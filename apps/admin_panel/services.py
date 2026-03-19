from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.economy.models import Transaction
from apps.economy.services import mint_coins, poker_payout

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


def admin_deduct_coins(
    admin_user: User,
    target_user: User,
    amount: int,
    note: str = '',
) -> Transaction:
    """Atomically deduct coins from a user. Clamps to 0 if balance insufficient."""
    if amount <= 0:
        raise ValueError('Amount must be positive.')

    with transaction.atomic():
        profile = UserProfile.objects.select_for_update().get(user=target_user)
        actual = min(amount, profile.balance)
        profile.balance -= actual
        profile.save(update_fields=['balance'])

        tx = Transaction.objects.create(
            sender=target_user,
            receiver=None,
            amount=actual,
            tx_type='mint',
            note=note or f'Admin deduction by {admin_user.username}',
        )

        logger.info(
            'Admin deduction: admin=%s target=%s requested=%d actual=%d',
            admin_user.username, target_user.username, amount, actual,
        )
        return tx


def admin_cancel_coinflip(admin_user, challenge_id):
    """Cancel a coin flip challenge."""
    from apps.coinflip.models import CoinFlipChallenge

    with transaction.atomic():
        challenge = CoinFlipChallenge.objects.select_for_update().get(pk=challenge_id)
        challenge.status = 'cancelled'
        challenge.save(update_fields=['status'])

        logger.info(
            'Admin cancel coinflip: admin=%s challenge=%d',
            admin_user.username, challenge_id,
        )
        return challenge


def admin_cancel_chess(admin_user, game_id):
    """Cancel a chess game."""
    from apps.chess.models import ChessGame

    with transaction.atomic():
        game = ChessGame.objects.select_for_update().get(pk=game_id)
        game.status = 'cancelled'
        game.end_reason = 'cancelled'
        game.ended_at = timezone.now()
        game.save(update_fields=['status', 'end_reason', 'ended_at'])

        logger.info(
            'Admin cancel chess: admin=%s game=%d',
            admin_user.username, game_id,
        )
        return game


def admin_cancel_poker(admin_user, table_id):
    """Cancel a poker table and refund all players' invested coins."""
    from apps.poker.models import PokerTable

    with transaction.atomic():
        table = PokerTable.objects.select_for_update().get(pk=table_id)
        players = table.players.select_related('user').filter(coins_invested__gt=0)

        payouts = [(p.user, p.coins_invested) for p in players]
        if payouts:
            poker_payout(payouts, note=f'Admin cancelled table #{table_id}')

        table.status = 'cancelled'
        table.ended_at = timezone.now()
        table.save(update_fields=['status', 'ended_at'])

        logger.info(
            'Admin cancel poker: admin=%s table=%d refunded=%d players',
            admin_user.username, table_id, len(payouts),
        )
        return table


def admin_refund_game(
    admin_user: User,
    target_user: User,
    amount: int,
    game_type: str,
    game_id: int,
    note: str = '',
) -> Transaction:
    """Issue a refund by minting coins to a user with an audit note."""
    refund_note = note or f'Refund for {game_type} game #{game_id}'
    return mint_coins(
        admin_user=admin_user,
        target_user=target_user,
        amount=amount,
        note=refund_note,
    )
