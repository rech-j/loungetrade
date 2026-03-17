from django.contrib.auth.models import User
from django.test import TestCase, Client

from apps.accounts.models import UserProfile
from apps.poker.models import PokerPlayer, PokerTable


class LobbyViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass')
        self.client = Client()
        self.client.login(username='alice', password='pass')

    def test_lobby_loads(self):
        response = self.client.get('/poker/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Texas Hold')

    def test_lobby_requires_login(self):
        self.client.logout()
        response = self.client.get('/poker/')
        self.assertEqual(response.status_code, 302)


class CreateTableViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass')
        self.user.profile.balance = 500
        self.user.profile.save()
        self.client = Client()
        self.client.login(username='alice', password='pass')

    def test_create_public_table(self):
        response = self.client.post('/poker/create/', {
            'stake': 100,
            'is_public': 'on',
            'starting_chips': 1000,
            'small_blind': 10,
            'big_blind': 20,
            'max_players': 6,
            'min_players': 3,
            'time_per_action': 30,
            'max_rebuys': 0,
        })
        self.assertEqual(response.status_code, 302)
        table = PokerTable.objects.first()
        self.assertIsNotNone(table)
        self.assertTrue(table.is_public)
        self.assertEqual(table.stake, 100)
        # Creator should be at seat 0
        player = PokerPlayer.objects.get(table=table, user=self.user)
        self.assertEqual(player.seat, 0)
        self.assertEqual(player.chips, 1000)
        # Balance should be deducted
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 400)

    def test_create_insufficient_balance(self):
        self.user.profile.balance = 10
        self.user.profile.save()
        response = self.client.post('/poker/create/', {
            'stake': 100,
            'is_public': 'on',
            'starting_chips': 1000,
            'small_blind': 10,
            'big_blind': 20,
            'max_players': 6,
            'min_players': 3,
            'time_per_action': 30,
            'max_rebuys': 0,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PokerTable.objects.count(), 0)


class JoinTableViewTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user('alice', password='pass')
        self.creator.profile.balance = 500
        self.creator.profile.save()
        self.joiner = User.objects.create_user('bob', password='pass')
        self.joiner.profile.balance = 500
        self.joiner.profile.save()

        self.table = PokerTable.objects.create(
            creator=self.creator, stake=100, is_public=True,
        )
        PokerPlayer.objects.create(
            table=self.table, user=self.creator, seat=0,
            chips=1000, status='active', coins_invested=100,
        )

        self.client = Client()
        self.client.login(username='bob', password='pass')

    def test_join_public_table(self):
        response = self.client.post(f'/poker/join/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        player = PokerPlayer.objects.get(table=self.table, user=self.joiner)
        self.assertEqual(player.seat, 1)
        self.joiner.profile.refresh_from_db()
        self.assertEqual(self.joiner.profile.balance, 400)

    def test_cannot_join_private_table(self):
        self.table.is_public = False
        self.table.save()
        response = self.client.post(f'/poker/join/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PokerPlayer.objects.filter(table=self.table, user=self.joiner).exists())


class LeaveTableViewTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user('alice', password='pass')
        self.creator.profile.balance = 400
        self.creator.profile.save()
        self.table = PokerTable.objects.create(
            creator=self.creator, stake=100,
        )
        PokerPlayer.objects.create(
            table=self.table, user=self.creator, seat=0,
            chips=1000, status='active', coins_invested=100,
        )
        self.client = Client()
        self.client.login(username='alice', password='pass')

    def test_creator_leave_cancels_table(self):
        response = self.client.post(f'/poker/leave/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'cancelled')
        self.creator.profile.refresh_from_db()
        self.assertEqual(self.creator.profile.balance, 500)  # refunded
