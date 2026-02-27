import json
import logging
import secrets

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from apps.economy.services import InsufficientFunds, game_transfer
from apps.notifications.models import Notification

from .models import ChessGame

logger = logging.getLogger(__name__)


class ChessConsumer(AsyncWebsocketConsumer):
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

        # If game is still pending, check if we should activate it
        if game.status == 'pending' and game.creator_id == self.user.pk:
            # Creator connected — just notify the room
            pass
        elif game.status == 'pending' and game.opponent_id == self.user.pk:
            # Opponent connected — both players ready, start the game
            await self.activate_game(game)
            game = await self.get_game()

        # Send current game state to the newly connected player
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'status': game.status,
            'fen': game.fen,
            'moves_uci': game.moves_uci,
            'white_player': game.white_player.username if game.white_player else None,
            'black_player': game.black_player.username if game.black_player else None,
            'white_time': game.white_time,
            'black_time': game.black_time,
            'your_side': game.get_player_side(self.user) if game.white_player and game.black_player else None,
        }))

        if game.status == 'active':
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'player_connected',
                'username': self.user.username,
            })

    async def disconnect(self, close_code):
        logger.info('Chess WS disconnected: user=%s game=%s', getattr(self, 'user', None), self.game_id)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
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
        """Relay a move to the other player and save it."""
        game = await self.get_game()
        if not game or game.status != 'active':
            return

        side = game.get_player_side(self.user)
        move_uci = data.get('move', '').strip()
        fen_after = data.get('fen', '').strip()
        white_time = data.get('white_time')
        black_time = data.get('black_time')

        if not move_uci or not fen_after:
            return

        # Validate it's this player's turn
        # FEN turn is the character after the first space: 'w' or 'b'
        parts = game.fen.split(' ')
        current_turn = parts[1] if len(parts) > 1 else 'w'
        if (current_turn == 'w' and side != 'white') or (current_turn == 'b' and side != 'black'):
            return

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

        await self.finish_game(game.pk, winner.pk, 'resign')
        try:
            await self.do_game_transfer(winner.pk, loser.pk, game.stake)
        except InsufficientFunds:
            await self.cancel_game_db(game.pk)
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'chess_error',
                'message': 'Game cancelled — insufficient balance.',
            })
            return

        await self.create_chess_notifications(game, winner, loser, 'resign')

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chess_game_over',
            'winner': winner.username,
            'reason': 'resign',
            'stake': game.stake,
        })

    async def handle_timeout(self, data):
        """A player's clock ran out (as reported by the frontend)."""
        game = await self.get_game()
        if not game or game.status != 'active':
            return

        timed_out_side = data.get('side')  # 'white' or 'black'
        winner = game.black_player if timed_out_side == 'white' else game.white_player
        loser = game.white_player if timed_out_side == 'white' else game.black_player

        await self.finish_game(game.pk, winner.pk, 'timeout')
        try:
            await self.do_game_transfer(winner.pk, loser.pk, game.stake)
        except InsufficientFunds:
            await self.cancel_game_db(game.pk)
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'chess_error',
                'message': 'Game cancelled — insufficient balance.',
            })
            return

        await self.create_chess_notifications(game, winner, loser, 'timeout')

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chess_game_over',
            'winner': winner.username,
            'reason': 'timeout',
            'stake': game.stake,
        })

    async def handle_game_over(self, data):
        """Checkmate or stalemate reported by frontend chess.js."""
        game = await self.get_game()
        if not game or game.status != 'active':
            return

        reason = data.get('reason', 'checkmate')  # checkmate, stalemate, draw
        winner_username = data.get('winner')  # None for stalemate/draw

        if reason in ('stalemate', 'draw'):
            # Draw — refund stake (no transfer, just end game)
            await self.finish_game(game.pk, None, reason)
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'chess_game_over',
                'winner': None,
                'reason': reason,
                'stake': game.stake,
            })
            return

        # Checkmate — find winner
        if winner_username == (game.white_player.username if game.white_player else None):
            winner = game.white_player
            loser = game.black_player
        else:
            winner = game.black_player
            loser = game.white_player

        if not winner or not loser:
            return

        await self.finish_game(game.pk, winner.pk, reason)
        try:
            await self.do_game_transfer(winner.pk, loser.pk, game.stake)
        except InsufficientFunds:
            await self.cancel_game_db(game.pk)
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'chess_error',
                'message': 'Game cancelled — insufficient balance.',
            })
            return

        await self.create_chess_notifications(game, winner, loser, reason)

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chess_game_over',
            'winner': winner.username,
            'reason': reason,
            'stake': game.stake,
        })

    # ── Channel layer event handlers ────────────────────────────────────────

    async def player_connected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_connected',
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

    async def chess_error(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chess_error',
            'message': event['message'],
        }))

    # ── Database helpers ─────────────────────────────────────────────────────

    @database_sync_to_async
    def get_game(self):
        try:
            return ChessGame.objects.select_related(
                'white_player', 'black_player', 'creator', 'opponent'
            ).get(pk=self.game_id)
        except ChessGame.DoesNotExist:
            return None

    @database_sync_to_async
    def activate_game(self, game):
        import random as _random
        """Assign colors and mark game active when opponent connects."""
        if game.status != 'pending':
            return
        side = game.creator_side
        if side == 'random':
            side = _random.choice(['white', 'black'])

        if side == 'white':
            white_id = game.creator_id
            black_id = game.opponent_id
        else:
            white_id = game.opponent_id
            black_id = game.creator_id

        ChessGame.objects.filter(pk=game.pk).update(
            status='active',
            white_player_id=white_id,
            black_player_id=black_id,
            started_at=timezone.now(),
        )

    @database_sync_to_async
    def save_move(self, game_id, move_uci, fen_after, white_time, black_time):
        from django.db.models import F
        game = ChessGame.objects.get(pk=game_id)
        moves = (game.moves_uci + ' ' + move_uci).strip()
        update = {
            'fen': fen_after,
            'moves_uci': moves,
            'last_move_at': timezone.now(),
        }
        if white_time is not None:
            update['white_time'] = int(white_time)
        if black_time is not None:
            update['black_time'] = int(black_time)
        ChessGame.objects.filter(pk=game_id).update(**update)

    @database_sync_to_async
    def finish_game(self, game_id, winner_id, reason):
        ChessGame.objects.filter(pk=game_id).update(
            status='completed',
            winner_id=winner_id,
            end_reason=reason,
            ended_at=timezone.now(),
        )

    @database_sync_to_async
    def cancel_game_db(self, game_id):
        ChessGame.objects.filter(pk=game_id).update(
            status='cancelled',
            end_reason='cancelled',
            ended_at=timezone.now(),
        )

    @database_sync_to_async
    def do_game_transfer(self, winner_id, loser_id, stake):
        from django.contrib.auth.models import User
        winner = User.objects.get(pk=winner_id)
        loser = User.objects.get(pk=loser_id)
        game_transfer(winner, loser, stake)

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
