import json
import logging

import chess
from channels.db import database_sync_to_async
from django.utils import timezone

from apps.economy.services import InsufficientFunds
from apps.games.mixins import BaseGameConsumer
from apps.notifications.models import Notification

from .models import ChessGame

logger = logging.getLogger(__name__)


class ChessConsumer(BaseGameConsumer):
    game_type = 'chess'

    async def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f'chess_{self.game_id}'
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        game = await self.get_game()
        if not game:
            await self.close()
            return

        if self.user.pk not in (game.creator_id, game.opponent_id):
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        logger.info('Chess WS connected: user=%s game=%s', self.user.username, self.game_id)

        just_activated = False
        # If game is still pending, check if we should activate it
        if game.status == 'pending' and game.creator_id == self.user.pk:
            # Creator connected - just notify the room
            pass
        elif game.status == 'pending' and game.opponent_id == self.user.pk:
            # Opponent connected - both players ready, start the game
            just_activated = await self.activate_game(game)
            if just_activated:
                game = await self.get_game()

        if just_activated:
            # Broadcast updated game_state to ALL players in the room so the
            # creator (who was waiting in pending state) also receives active state.
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'game_activated',
            })
        else:
            # Send current game state only to the newly connected player
            white_time, black_time = self.get_adjusted_times(game)
            await self.send(text_data=json.dumps({
                'type': 'game_state',
                'status': game.status,
                'fen': game.fen,
                'moves_uci': game.moves_uci,
                'white_player': game.white_player.username if game.white_player else None,
                'black_player': game.black_player.username if game.black_player else None,
                'white_time': white_time,
                'black_time': black_time,
                'your_side': game.get_player_side(self.user) if game.white_player and game.black_player else None,
            }))

            if game.status == 'active':
                await self.channel_layer.group_send(self.room_group_name, {
                    'type': 'player_connected',
                    'username': self.user.username,
                })

    async def disconnect(self, close_code):
        logger.info('Chess WS disconnected: user=%s game=%s', getattr(self, 'user', None), self.game_id)
        if hasattr(self, 'user') and not self.user.is_anonymous:
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'player_disconnected',
                'username': self.user.username,
            })
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        if self.is_throttled():
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = data.get('action')

        if action == 'move':
            await self.handle_move(data)
        elif action == 'resign':
            await self.handle_resign()
        elif action == 'timeout':
            await self.handle_timeout(data)
        elif action == 'game_over':
            await self.handle_game_over(data)

    async def handle_move(self, data):
        """Validate and relay a move to the other player.

        Uses python-chess for server-side move validation.  The FEN after the
        move is computed on the server - the client-supplied 'fen' field is
        intentionally ignored to prevent game-state forgery.
        """
        game = await self.get_game()
        if not game or game.status != 'active':
            return

        side = game.get_player_side(self.user)
        move_uci = data.get('move', '').strip()
        white_time = data.get('white_time')
        black_time = data.get('black_time')

        if not move_uci:
            return

        # Server-side validation via python-chess
        try:
            board = chess.Board(game.fen)
        except ValueError:
            logger.warning('Corrupt FEN in game %s: %s', game.pk, game.fen)
            return

        # Validate it's this player's turn
        if (board.turn == chess.WHITE and side != 'white') or \
           (board.turn == chess.BLACK and side != 'black'):
            return

        # Parse and validate the move
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            return

        if move not in board.legal_moves:
            logger.warning(
                'Illegal move rejected: game=%s user=%s move=%s fen=%s',
                game.pk, self.user.username, move_uci, game.fen,
            )
            return

        # Apply the move and derive the authoritative FEN server-side
        board.push(move)
        fen_after = board.fen()

        await self.save_move(game.pk, move_uci, fen_after, white_time, black_time)

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chess_move',
            'move': move_uci,
            'fen': fen_after,
            'player': self.user.username,
            'white_time': white_time,
            'black_time': black_time,
        })

    async def handle_resign(self):
        game = await self.get_game()
        if not game or game.status != 'active':
            return

        side = game.get_player_side(self.user)
        winner = game.black_player if side == 'white' else game.white_player
        loser = self.user

        finished = await self.finish_game(game.pk, winner.pk, 'resign')
        if not finished:
            return
        try:
            await self.do_game_transfer(winner.pk, loser.pk, game.stake, note='Chess - resignation')
        except InsufficientFunds:
            await self.cancel_game_db(game.pk)
            await self.broadcast_error('Game cancelled - insufficient balance.')
            return

        await self.create_chess_notifications(game, winner, loser, 'resign')

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chess_game_over',
            'winner': winner.username,
            'reason': 'resign',
            'stake': game.stake,
        })

    async def handle_timeout(self, data):
        """A player's clock ran out (as reported by the frontend).

        Only self-reported timeouts are accepted - the reporting player is
        treated as the one who timed out, regardless of any 'side' field in
        the message.  This prevents a player from falsely claiming their
        opponent timed out to steal the stake.
        """
        game = await self.get_game()
        if not game or game.status != 'active':
            return

        # Derive timed-out side from who is reporting, not from client data.
        reporting_side = game.get_player_side(self.user)
        if not reporting_side:
            return

        if reporting_side == 'white':
            winner = game.black_player
            loser = game.white_player
        else:
            winner = game.white_player
            loser = game.black_player

        finished = await self.finish_game(game.pk, winner.pk, 'timeout')
        if not finished:
            return
        try:
            await self.do_game_transfer(winner.pk, loser.pk, game.stake, note='Chess - timeout')
        except InsufficientFunds:
            await self.cancel_game_db(game.pk)
            await self.broadcast_error('Game cancelled - insufficient balance.')
            return

        await self.create_chess_notifications(game, winner, loser, 'timeout')

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chess_game_over',
            'winner': winner.username,
            'reason': 'timeout',
            'stake': game.stake,
        })

    async def handle_game_over(self, data):
        """Checkmate or stalemate reported by frontend chess.js.

        Only accepted from the player who just moved.  The FEN's active-side
        character shows whose turn it is NEXT, so the other side just moved.
        Winner for checkmate is server-derived (the last mover) - the client's
        'winner' field is intentionally ignored to prevent result forgery.
        """
        game = await self.get_game()
        if not game or game.status != 'active':
            return

        # Determine who just moved from the stored FEN (server-side truth).
        parts = game.fen.split(' ')
        next_turn = parts[1] if len(parts) > 1 else 'w'
        just_moved_side = 'black' if next_turn == 'w' else 'white'

        reporting_side = game.get_player_side(self.user)
        if reporting_side != just_moved_side:
            # Only the player who just moved may report game-over.
            return

        reason = data.get('reason', 'checkmate')  # checkmate, stalemate, draw

        if reason in ('stalemate', 'draw'):
            # Draw - no coin transfer, just end the game.
            finished = await self.finish_game(game.pk, None, reason)
            if not finished:
                return
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'chess_game_over',
                'winner': None,
                'reason': reason,
                'stake': game.stake,
            })
            return

        # Checkmate - winner is the player who just moved (server-derived).
        if just_moved_side == 'white':
            winner = game.white_player
            loser = game.black_player
        else:
            winner = game.black_player
            loser = game.white_player

        if not winner or not loser:
            return

        finished = await self.finish_game(game.pk, winner.pk, reason)
        if not finished:
            return
        try:
            await self.do_game_transfer(
                winner.pk, loser.pk, game.stake,
                note=f'Chess - {reason}',
            )
        except InsufficientFunds:
            await self.cancel_game_db(game.pk)
            await self.broadcast_error('Game cancelled - insufficient balance.')
            return

        await self.create_chess_notifications(game, winner, loser, reason)

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chess_game_over',
            'winner': winner.username,
            'reason': reason,
            'stake': game.stake,
        })

    # ── Channel layer event handlers ────────────────────────────────────────

    async def game_activated(self, event):
        """Sent to the whole group when the game transitions pending → active."""
        game = await self.get_game()
        if not game:
            return
        white_time, black_time = self.get_adjusted_times(game)
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'status': game.status,
            'fen': game.fen,
            'moves_uci': game.moves_uci,
            'white_player': game.white_player.username if game.white_player else None,
            'black_player': game.black_player.username if game.black_player else None,
            'white_time': white_time,
            'black_time': black_time,
            'your_side': game.get_player_side(self.user) if game.white_player and game.black_player else None,
        }))

    async def player_connected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_connected',
            'username': event['username'],
        }))

    async def player_disconnected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_disconnected',
            'username': event['username'],
        }))

    async def chess_move(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chess_move',
            'move': event['move'],
            'fen': event['fen'],
            'player': event['player'],
            'white_time': event['white_time'],
            'black_time': event['black_time'],
        }))

    async def chess_game_over(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chess_game_over',
            'winner': event['winner'],
            'reason': event['reason'],
            'stake': event['stake'],
        }))

    async def game_error(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chess_error',
            'message': event['message'],
        }))

    # ── Time helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def get_adjusted_times(game):
        """Return (white_time, black_time) adjusted for elapsed time since last move.

        The DB stores the clock values as of the last move.  If a game is
        active, the current player's clock has been ticking since then.
        """
        white_time = game.white_time
        black_time = game.black_time
        if game.status == 'active' and game.last_move_at:
            elapsed = (timezone.now() - game.last_move_at).total_seconds()
            # Determine whose clock is running from the FEN active color
            parts = game.fen.split(' ')
            active_color = parts[1] if len(parts) > 1 else 'w'
            if active_color == 'w':
                white_time = max(0, int(white_time - elapsed))
            else:
                black_time = max(0, int(black_time - elapsed))
        return white_time, black_time

    # ── Database helpers ─────────────────────────────────────────────────────

    @database_sync_to_async
    def get_game(self):
        try:
            return ChessGame.objects.select_related(
                'white_player__profile', 'black_player__profile',
                'creator', 'opponent',
            ).get(pk=self.game_id)
        except ChessGame.DoesNotExist:
            return None

    @database_sync_to_async
    def activate_game(self, game):
        """Assign colors and mark game active when opponent connects.

        Uses a conditional update (status='pending') to prevent double
        activation from concurrent WebSocket connections (TOCTOU guard).
        Returns True if this call activated the game, False otherwise.
        """
        import random as _random
        side = game.creator_side
        if side == 'random':
            side = _random.choice(['white', 'black'])

        if side == 'white':
            white_id = game.creator_id
            black_id = game.opponent_id
        else:
            white_id = game.opponent_id
            black_id = game.creator_id

        updated = ChessGame.objects.filter(pk=game.pk, status='pending').update(
            status='active',
            white_player_id=white_id,
            black_player_id=black_id,
            started_at=timezone.now(),
        )
        return updated > 0

    @database_sync_to_async
    def save_move(self, game_id, move_uci, fen_after, white_time, black_time):
        game = ChessGame.objects.get(pk=game_id)
        moves = (game.moves_uci + ' ' + move_uci).strip()
        update = {
            'fen': fen_after,
            'moves_uci': moves,
            'last_move_at': timezone.now(),
        }
        # Only accept times that are non-negative and not higher than the
        # current stored value — prevents clients from inflating their clock.
        if white_time is not None:
            wt = int(white_time)
            if 0 <= wt <= game.white_time:
                update['white_time'] = wt
        if black_time is not None:
            bt = int(black_time)
            if 0 <= bt <= game.black_time:
                update['black_time'] = bt
        ChessGame.objects.filter(pk=game_id).update(**update)

    @database_sync_to_async
    def finish_game(self, game_id, winner_id, reason):
        """Atomically transition active → completed (TOCTOU guard).

        Returns True if this call performed the update.
        """
        updated = ChessGame.objects.filter(pk=game_id, status='active').update(
            status='completed',
            winner_id=winner_id,
            end_reason=reason,
            ended_at=timezone.now(),
        )
        return updated > 0

    @database_sync_to_async
    def cancel_game_db(self, game_id):
        ChessGame.objects.filter(pk=game_id).update(
            status='cancelled',
            end_reason='cancelled',
            ended_at=timezone.now(),
        )

    @database_sync_to_async
    def create_chess_notifications(self, game, winner, loser, reason):
        reason_text = {
            'checkmate': 'checkmate',
            'resign': 'resignation',
            'timeout': 'timeout',
        }.get(reason, reason)
        Notification.objects.create(
            user=winner,
            notif_type='game_result',
            title='Chess Win!',
            message=f'You won {game.stake} LC from {loser.profile.get_display_name()} by {reason_text}.',
            link='/chess/',
        )
        Notification.objects.create(
            user=loser,
            notif_type='game_result',
            title='Chess Defeat',
            message=f'You lost {game.stake} LC to {winner.profile.get_display_name()} by {reason_text}.',
            link='/chess/',
        )
