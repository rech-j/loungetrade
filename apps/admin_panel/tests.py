from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.chess.models import ChessGame
from apps.coinflip.models import CoinFlipChallenge
from apps.economy.models import Transaction
from apps.poker.models import PokerPlayer, PokerTable

from .services import admin_cancel_chess, admin_cancel_coinflip, admin_deduct_coins


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminPanelTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', 'admin@test.com', 'pass')
        self.admin.profile.is_admin_user = True
        self.admin.profile.balance = 1000
        self.admin.profile.save()

        self.user = User.objects.create_user('user1', 'user1@test.com', 'pass')
        self.user.profile.balance = 500
        self.user.profile.save()


class AccessControlTest(AdminPanelTestCase):
    """Non-admin users should get 403 on all admin panel views."""

    def test_dashboard_requires_admin(self):
        self.client.login(username='user1', password='pass')
        resp = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_user_list_requires_admin(self):
        self.client.login(username='user1', password='pass')
        resp = self.client.get(reverse('admin_users'))
        self.assertEqual(resp.status_code, 403)

    def test_games_requires_admin(self):
        self.client.login(username='user1', password='pass')
        resp = self.client.get(reverse('admin_games'))
        self.assertEqual(resp.status_code, 403)

    def test_transactions_requires_admin(self):
        self.client.login(username='user1', password='pass')
        resp = self.client.get(reverse('admin_transactions'))
        self.assertEqual(resp.status_code, 403)

    def test_economy_stats_requires_admin(self):
        self.client.login(username='user1', password='pass')
        resp = self.client.get(reverse('admin_economy_stats'))
        self.assertEqual(resp.status_code, 403)


class DashboardTest(AdminPanelTestCase):
    def test_dashboard_loads(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Dashboard')

    def test_live_stats_partial(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_stats_partial'))
        self.assertEqual(resp.status_code, 200)


class UserManagementTest(AdminPanelTestCase):
    def test_user_list(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_users'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'user1')

    def test_user_search(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_users'), {'q': 'user1'})
        self.assertContains(resp, 'user1')

    def test_user_detail(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_user_detail', kwargs={'user_id': self.user.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'user1')

    def test_adjust_balance_positive(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.post(
            reverse('admin_adjust_balance', kwargs={'user_id': self.user.pk}),
            {'amount': 100, 'note': 'Test mint'},
        )
        self.assertEqual(resp.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 600)

    def test_adjust_balance_negative(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.post(
            reverse('admin_adjust_balance', kwargs={'user_id': self.user.pk}),
            {'amount': -200, 'note': 'Test deduction'},
        )
        self.assertEqual(resp.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 300)

    def test_adjust_balance_clamps_to_zero(self):
        self.client.login(username='admin', password='pass')
        self.client.post(
            reverse('admin_adjust_balance', kwargs={'user_id': self.user.pk}),
            {'amount': -9999, 'note': 'Overdraw'},
        )
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 0)

    def test_toggle_admin(self):
        self.client.login(username='admin', password='pass')
        self.assertFalse(self.user.profile.is_admin_user)
        self.client.post(reverse('admin_toggle_admin', kwargs={'user_id': self.user.pk}))
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.is_admin_user)

    def test_toggle_admin_self_protection(self):
        self.client.login(username='admin', password='pass')
        self.client.post(reverse('admin_toggle_admin', kwargs={'user_id': self.admin.pk}))
        self.admin.profile.refresh_from_db()
        self.assertTrue(self.admin.profile.is_admin_user)  # unchanged

    def test_toggle_active(self):
        self.client.login(username='admin', password='pass')
        self.assertTrue(self.user.is_active)
        self.client.post(reverse('admin_toggle_active', kwargs={'user_id': self.user.pk}))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_toggle_active_self_protection(self):
        self.client.login(username='admin', password='pass')
        self.client.post(reverse('admin_toggle_active', kwargs={'user_id': self.admin.pk}))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)  # unchanged


class GameManagementTest(AdminPanelTestCase):
    def setUp(self):
        super().setUp()
        self.coinflip = CoinFlipChallenge.objects.create(
            challenger=self.admin,
            opponent=self.user,
            stake=100,
            status='pending',
            challenger_choice='heads',
        )
        self.chess = ChessGame.objects.create(
            creator=self.admin,
            opponent=self.user,
            stake=200,
            status='active',
        )

    def test_game_list(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_games'))
        self.assertEqual(resp.status_code, 200)

    def test_game_list_filter_type(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_games'), {'type': 'coinflip'})
        self.assertContains(resp, 'Coin Flip')

    def test_coinflip_detail(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_game_detail', kwargs={
            'game_type': 'coinflip', 'game_id': self.coinflip.pk,
        }))
        self.assertEqual(resp.status_code, 200)

    def test_chess_detail(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_game_detail', kwargs={
            'game_type': 'chess', 'game_id': self.chess.pk,
        }))
        self.assertEqual(resp.status_code, 200)

    def test_cancel_coinflip(self):
        self.client.login(username='admin', password='pass')
        self.client.post(reverse('admin_cancel_game', kwargs={
            'game_type': 'coinflip', 'game_id': self.coinflip.pk,
        }))
        self.coinflip.refresh_from_db()
        self.assertEqual(self.coinflip.status, 'cancelled')

    def test_cancel_chess(self):
        self.client.login(username='admin', password='pass')
        self.client.post(reverse('admin_cancel_game', kwargs={
            'game_type': 'chess', 'game_id': self.chess.pk,
        }))
        self.chess.refresh_from_db()
        self.assertEqual(self.chess.status, 'cancelled')
        self.assertEqual(self.chess.end_reason, 'cancelled')
        self.assertIsNotNone(self.chess.ended_at)


class EconomyTest(AdminPanelTestCase):
    def setUp(self):
        super().setUp()
        Transaction.objects.create(
            sender=None, receiver=self.user, amount=500,
            tx_type='mint', note='Initial',
        )

    def test_transaction_list(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_transactions'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Mint')

    def test_transaction_filter_type(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_transactions'), {'type': 'mint'})
        self.assertContains(resp, 'user1')

    def test_economy_stats(self):
        self.client.login(username='admin', password='pass')
        resp = self.client.get(reverse('admin_economy_stats'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Coins in Circulation')


class ServiceTest(AdminPanelTestCase):
    def test_admin_deduct_coins(self):
        tx = admin_deduct_coins(self.admin, self.user, 200, 'Test deduct')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 300)
        self.assertEqual(tx.amount, 200)

    def test_admin_deduct_clamps(self):
        tx = admin_deduct_coins(self.admin, self.user, 9999, 'Overdraw')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 0)
        self.assertEqual(tx.amount, 500)

    def test_admin_cancel_coinflip_service(self):
        challenge = CoinFlipChallenge.objects.create(
            challenger=self.admin, opponent=self.user,
            stake=100, status='pending', challenger_choice='heads',
        )
        result = admin_cancel_coinflip(self.admin, challenge.pk)
        self.assertEqual(result.status, 'cancelled')

    def test_admin_cancel_chess_service(self):
        game = ChessGame.objects.create(
            creator=self.admin, opponent=self.user,
            stake=200, status='active',
        )
        result = admin_cancel_chess(self.admin, game.pk)
        self.assertEqual(result.status, 'cancelled')
        self.assertEqual(result.end_reason, 'cancelled')
        self.assertIsNotNone(result.ended_at)
