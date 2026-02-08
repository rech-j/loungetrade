from django.db import transaction

from apps.accounts.models import UserProfile
from apps.notifications.models import Notification

from .models import Transaction


class InsufficientFunds(Exception):
    pass


class InvalidTrade(Exception):
    pass


def transfer_coins(sender, receiver, amount, tx_type='trade', note=''):
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

        return tx


def mint_coins(admin_user, target_user, amount, note=''):
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

        return tx


def game_transfer(winner, loser, stake):
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

        # Single transaction record: coins flow from loser to winner
        Transaction.objects.create(
            sender=loser,
            receiver=winner,
            amount=stake,
            tx_type='game_win',
            note='Coin flip',
        )
