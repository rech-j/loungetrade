"""Management command to enforce server-side chess timeouts.

Finds active chess games where the current player's clock has expired
and ends them automatically. Intended to run via cron every ~60 seconds.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import F, Q
from django.utils import timezone

from apps.chess.models import ChessGame
from apps.economy.services import InsufficientFunds, game_transfer
from apps.notifications.services import send_notification


class Command(BaseCommand):
    help = 'End active chess games where a player has run out of time'

    def handle(self, *args, **options):
        now = timezone.now()
        timed_out = 0

        # Find active games that have had at least one move
        active_games = ChessGame.objects.filter(
            status='active',
            last_move_at__isnull=False,
        ).select_related('white_player', 'black_player')

        for game in active_games:
            elapsed = (now - game.last_move_at).total_seconds()

            # Determine whose clock is running from the FEN active color
            parts = game.fen.split(' ')
            active_color = parts[1] if len(parts) > 1 else 'w'

            if active_color == 'w':
                remaining = game.white_time - elapsed
                if remaining > 0:
                    continue
                # White's clock expired - black wins
                winner = game.black_player
                loser = game.white_player
            else:
                remaining = game.black_time - elapsed
                if remaining > 0:
                    continue
                # Black's clock expired - white wins
                winner = game.white_player
                loser = game.black_player

            if not winner or not loser:
                continue

            # Atomically transition active -> completed (TOCTOU guard)
            updated = ChessGame.objects.filter(
                pk=game.pk, status='active',
            ).update(
                status='completed',
                winner=winner,
                end_reason='timeout',
                ended_at=now,
            )
            if not updated:
                continue

            timed_out += 1

            # Transfer coins
            try:
                game_transfer(winner, loser, game.stake, note='Chess - timeout')
            except InsufficientFunds:
                ChessGame.objects.filter(pk=game.pk).update(
                    status='cancelled',
                    end_reason='cancelled',
                    ended_at=now,
                )
                continue

            # Notify players
            reason_text = 'timeout'
            send_notification(
                winner,
                'game_result',
                'Chess Win!',
                f'You won {game.stake} LC from {loser.profile.get_display_name()} by {reason_text}.',
                link='/chess/',
            )
            send_notification(
                loser,
                'game_result',
                'Chess Defeat',
                f'You lost {game.stake} LC to {winner.profile.get_display_name()} by {reason_text}.',
                link='/chess/',
            )

        self.stdout.write(self.style.SUCCESS(f'Timed out {timed_out} game(s).'))
