from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from apps.accounts.models import UserProfile
from apps.notifications.models import Notification

from .models import Transaction

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class InsufficientFunds(Exception):
    pass


class InvalidTrade(Exception):
    pass


def transfer_coins(
    sender: User,
    receiver: User,
    amount: int,
    tx_type: str = 'trade',
    note: str = '',
) -> Transaction:
    """Atomically transfer coins between users."""
    if sender == receiver:
        raise InvalidTrade('Cannot send coins to yourself.')
    if amount <= 0:
        raise InvalidTrade('Amount must be positive.')

    with transaction.atomic():
        sender_profile = UserProfile.objects.select_for_update().get(user=sender)
        receiver_profile = UserProfile.objects.select_for_update().get(user=receiver)

        if sender_profile.balance < amount:
            raise InsufficientFunds(
                f'Insufficient balance. You have {sender_profile.balance} coins.'
            )

        sender_profile.balance -= amount
        receiver_profile.balance += amount
        sender_profile.save(update_fields=['balance'])
        receiver_profile.save(update_fields=['balance'])

        tx = Transaction.objects.create(
            sender=sender,
            receiver=receiver,
            amount=amount,
            tx_type=tx_type,
            note=note,
        )

        Notification.objects.create(
            user=receiver,
            notif_type='coin_received',
            title='Coins Received',
            message=f'{sender_profile.get_display_name()} sent you {amount} coins.',
            link='/profile/',
        )

        logger.info(
            'Transfer: sender=%s receiver=%s amount=%d',
            sender.username, receiver.username, amount,
        )

        return tx


def mint_coins(
    admin_user: User,
    target_user: User,
    amount: int,
    note: str = '',
) -> Transaction:
    """Admin mints coins to a target user."""
    if amount <= 0:
        raise InvalidTrade('Amount must be positive.')

    with transaction.atomic():
        target_profile = UserProfile.objects.select_for_update().get(user=target_user)
        target_profile.balance += amount
        target_profile.save(update_fields=['balance'])

        tx = Transaction.objects.create(
            sender=None,
            receiver=target_user,
            amount=amount,
            tx_type='mint',
            note=note or f'Minted by {admin_user.username}',
        )

        Notification.objects.create(
            user=target_user,
            notif_type='coin_received',
            title='Coins Minted',
            message=f'An admin minted {amount} coins to your account.',
            link='/profile/',
        )

        logger.info(
            'Mint: admin=%s target=%s amount=%d',
            admin_user.username, target_user.username, amount,
        )

        return tx


def game_transfer(winner: User, loser: User, stake: int) -> None:
    """Transfer coins after a game result."""
    with transaction.atomic():
        loser_profile = UserProfile.objects.select_for_update().get(user=loser)
        winner_profile = UserProfile.objects.select_for_update().get(user=winner)

        if loser_profile.balance < stake:
            raise InsufficientFunds(
                f'{loser.username} no longer has enough coins for the stake.'
            )

        loser_profile.balance -= stake
        winner_profile.balance += stake
        loser_profile.save(update_fields=['balance'])
        winner_profile.save(update_fields=['balance'])

        # Record from winner's perspective
        Transaction.objects.create(
            sender=loser,
            receiver=winner,
            amount=stake,
            tx_type='game_win',
            note='Coin flip',
        )

        # Record from loser's perspective
        Transaction.objects.create(
            sender=loser,
            receiver=winner,
            amount=stake,
            tx_type='game_loss',
            note='Coin flip',
        )

        logger.info(
            'Game transfer: winner=%s loser=%s stake=%d',
            winner.username, loser.username, stake,
        )
