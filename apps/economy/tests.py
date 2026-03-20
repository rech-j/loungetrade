from django.contrib.auth.models import User
from django.core.cache import cache
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

    def test_non_admin_cannot_mint(self):
        """Service layer rejects minting by non-admin users."""
        with self.assertRaises(InvalidTrade):
            mint_coins(self.user, self.admin, 100)
        self.admin.profile.refresh_from_db()
        self.assertEqual(self.admin.profile.balance, 0)


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
        game_transfer(self.alice, self.bob, 50, note='Coin flip')
        self.assertEqual(Transaction.objects.count(), 1)
        tx = Transaction.objects.first()
        self.assertEqual(tx.sender, self.bob)  # loser
        self.assertEqual(tx.receiver, self.alice)  # winner
        self.assertEqual(tx.tx_type, 'game')
        self.assertEqual(tx.note, 'Coin flip')

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
        response = self.client.post('/economy/trade/', {
            'recipient_username': 'nobody',
            'amount': 10,
        })
        self.assertEqual(response.status_code, 200)
        self.alice.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 100)

    def test_trade_overdraft(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post('/economy/trade/', {
            'recipient_username': 'bob',
            'amount': 999,
        })
        self.assertEqual(response.status_code, 200)
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


class TransactionCascadeTest(TestCase):
    def test_deleting_receiver_preserves_transactions(self):
        """Deleting a user must not destroy transactions where they were the receiver."""
        alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        alice.profile.balance = 100
        alice.profile.save()
        transfer_coins(alice, bob, 50, note='test')
        tx_id = Transaction.objects.get(sender=alice, receiver=bob).pk
        bob.delete()
        tx = Transaction.objects.get(pk=tx_id)
        self.assertIsNone(tx.receiver)
        self.assertEqual(tx.amount, 50)


class TransactionHistoryViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        transfer_coins(self.alice, self.bob, 30, note='sent tx')

    def test_history_requires_login(self):
        response = self.client.get('/economy/history/')
        self.assertEqual(response.status_code, 302)

    def test_history_returns_200(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/economy/history/')
        self.assertEqual(response.status_code, 200)

    def test_history_filter_sent(self):
        self.client.login(username='bob', password='pass1234')
        # Bob received but did not send, so filtered sent list should be empty
        response = self.client.get('/economy/history/?filter=sent')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page'].paginator.count, 0)

    def test_history_filter_received(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.get('/economy/history/?filter=received')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page'].paginator.count, 1)


class ExportTransactionsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        transfer_coins(self.alice, self.bob, 25, note='csv test')

    def test_export_requires_login(self):
        response = self.client.get('/economy/export/')
        self.assertEqual(response.status_code, 302)

    def test_export_returns_csv_content_type(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/economy/export/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.get('Content-Type', ''))

    def test_export_only_contains_own_transactions(self):
        # Create a transaction that alice is not part of
        eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')
        self.bob.profile.balance = 50
        self.bob.profile.save()
        transfer_coins(self.bob, eve, 10, note='unrelated')

        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/economy/export/')
        content = b''.join(response.streaming_content).decode()

        self.assertIn('csv test', content)
        self.assertNotIn('unrelated', content)
