from django.contrib.auth.models import User
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.economy.models import Transaction
from apps.economy.services import (
    InsufficientFunds,
    InvalidTrade,
    game_transfer,
    mint_coins,
    transfer_coins,
)


class TransferCoinsTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()

    def test_successful_transfer(self):
        transfer_coins(self.alice, self.bob, 30, note='test')
        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 70)
        self.assertEqual(self.bob.profile.balance, 30)

    def test_insufficient_funds(self):
        with self.assertRaises(InsufficientFunds):
            transfer_coins(self.alice, self.bob, 200)
        self.alice.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 100)

    def test_self_transfer_rejected(self):
        with self.assertRaises(InvalidTrade):
            transfer_coins(self.alice, self.alice, 10)

    def test_zero_amount_rejected(self):
        with self.assertRaises(InvalidTrade):
            transfer_coins(self.alice, self.bob, 0)

    def test_negative_amount_rejected(self):
        with self.assertRaises(InvalidTrade):
            transfer_coins(self.alice, self.bob, -5)

    def test_notification_created(self):
        transfer_coins(self.alice, self.bob, 10)
        self.assertEqual(self.bob.notifications.count(), 1)

    def test_transaction_record_created(self):
        transfer_coins(self.alice, self.bob, 25, note='for lunch')
        tx = Transaction.objects.first()
        self.assertEqual(tx.sender, self.alice)
        self.assertEqual(tx.receiver, self.bob)
        self.assertEqual(tx.amount, 25)
        self.assertEqual(tx.tx_type, 'trade')
        self.assertEqual(tx.note, 'for lunch')


class MintCoinsTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', 'admin@test.com', 'pass1234')
        self.admin.profile.is_admin_user = True
        self.admin.profile.save()
        self.user = User.objects.create_user('user', 'user@test.com', 'pass1234')

    def test_successful_mint(self):
        mint_coins(self.admin, self.user, 500)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 500)

    def test_mint_creates_transaction(self):
        mint_coins(self.admin, self.user, 100)
        tx = Transaction.objects.first()
        self.assertIsNone(tx.sender)
        self.assertEqual(tx.receiver, self.user)
        self.assertEqual(tx.tx_type, 'mint')

    def test_zero_mint_rejected(self):
        with self.assertRaises(InvalidTrade):
            mint_coins(self.admin, self.user, 0)

    def test_mint_notification_created(self):
        mint_coins(self.admin, self.user, 50)
        self.assertEqual(self.user.notifications.count(), 1)
        notif = self.user.notifications.first()
        self.assertEqual(notif.notif_type, 'coin_received')


class GameTransferTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()

    def test_game_transfer_balances(self):
        game_transfer(self.alice, self.bob, 50)
        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 150)
        self.assertEqual(self.bob.profile.balance, 50)

    def test_game_transfer_creates_single_transaction(self):
        game_transfer(self.alice, self.bob, 50)
        self.assertEqual(Transaction.objects.count(), 1)
        tx = Transaction.objects.first()
        self.assertEqual(tx.sender, self.bob)  # loser
        self.assertEqual(tx.receiver, self.alice)  # winner
        self.assertEqual(tx.tx_type, 'game_win')

    def test_game_transfer_insufficient_funds(self):
        with self.assertRaises(InsufficientFunds):
            game_transfer(self.alice, self.bob, 200)


class TradeViewTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()

    def test_trade_post_success(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post('/economy/trade/', {
            'recipient_username': 'bob',
            'amount': 25,
            'note': 'test trade',
        })
        self.assertEqual(response.status_code, 200)
        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 75)
        self.assertEqual(self.bob.profile.balance, 25)

    def test_trade_nonexistent_user(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/economy/trade/', {
            'recipient_username': 'nobody',
            'amount': 10,
        })
        self.alice.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 100)

    def test_trade_overdraft(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/economy/trade/', {
            'recipient_username': 'bob',
            'amount': 999,
        })
        self.alice.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 100)


class MintViewTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', 'admin@test.com', 'pass1234')
        self.admin.profile.is_admin_user = True
        self.admin.profile.save()
        self.user = User.objects.create_user('user', 'user@test.com', 'pass1234')

    def test_non_admin_gets_403(self):
        self.client.login(username='user', password='pass1234')
        response = self.client.get('/economy/mint/')
        self.assertEqual(response.status_code, 403)

    def test_non_admin_post_gets_403(self):
        self.client.login(username='user', password='pass1234')
        response = self.client.post('/economy/mint/', {
            'recipient_username': 'admin',
            'amount': 999,
        })
        self.assertEqual(response.status_code, 403)

    def test_admin_can_mint(self):
        self.client.login(username='admin', password='pass1234')
        self.client.post('/economy/mint/', {
            'recipient_username': 'user',
            'amount': 200,
        })
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 200)
