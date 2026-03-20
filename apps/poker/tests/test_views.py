from django.contrib.auth.models import User
from django.test import TestCase

from apps.poker.models import PokerPlayer, PokerTable


class LobbyViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass')
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
        self.client.login(username='alice', password='pass')

    def _post(self, **kwargs):
        defaults = {
            'stake': 100,
            'is_public': 'on',
            'starting_chips': 1000,
            'small_blind': 10,
            'big_blind': 20,
            'max_players': 6,
            'min_players': 3,
            'time_per_action': 30,
            'max_rebuys': 0,
        }
        defaults.update(kwargs)
        return self.client.post('/poker/create/', defaults)

    def test_create_public_table(self):
        response = self._post()
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
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PokerTable.objects.count(), 0)

    def test_zero_stake_rejected(self):
        self._post(stake=0)
        self.assertEqual(PokerTable.objects.count(), 0)

    def test_negative_stake_rejected(self):
        self._post(stake=-50)
        self.assertEqual(PokerTable.objects.count(), 0)

    def test_stake_above_max_rejected(self):
        self.user.profile.balance = 99999
        self.user.profile.save()
        self._post(stake=10001)
        self.assertEqual(PokerTable.objects.count(), 0)

    def test_invalid_blind_values_rejected(self):
        self._post(small_blind=50, big_blind=10)
        self.assertEqual(PokerTable.objects.count(), 0)

    def test_starting_chips_too_low_rejected(self):
        self._post(starting_chips=100, big_blind=20)
        self.assertEqual(PokerTable.objects.count(), 0)

    def test_get_request_redirects(self):
        response = self.client.get('/poker/create/')
        self.assertEqual(response.status_code, 302)


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

    def test_insufficient_balance_on_join(self):
        self.joiner.profile.balance = 10
        self.joiner.profile.save()
        response = self.client.post(f'/poker/join/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            PokerPlayer.objects.filter(table=self.table, user=self.joiner).exists()
        )
        self.joiner.profile.refresh_from_db()
        self.assertEqual(self.joiner.profile.balance, 10)

    def test_accept_private_invite(self):
        self.table.is_public = False
        self.table.save()
        # Bob is invited
        PokerPlayer.objects.create(
            table=self.table, user=self.joiner, seat=1,
            chips=0, status='invited', coins_invested=0,
        )
        response = self.client.post(f'/poker/join/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        player = PokerPlayer.objects.get(table=self.table, user=self.joiner)
        self.assertEqual(player.status, 'active')
        self.assertEqual(player.chips, self.table.starting_chips)
        self.joiner.profile.refresh_from_db()
        self.assertEqual(self.joiner.profile.balance, 400)


class LeaveTableViewTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user('alice', password='pass')
        self.creator.profile.balance = 400
        self.creator.profile.save()
        self.joiner = User.objects.create_user('bob', password='pass')
        self.joiner.profile.balance = 400
        self.joiner.profile.save()
        self.table = PokerTable.objects.create(
            creator=self.creator, stake=100, is_public=True,
        )
        PokerPlayer.objects.create(
            table=self.table, user=self.creator, seat=0,
            chips=1000, status='active', coins_invested=100,
        )

    def test_creator_leave_cancels_table(self):
        self.client.login(username='alice', password='pass')
        response = self.client.post(f'/poker/leave/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'cancelled')
        self.creator.profile.refresh_from_db()
        self.assertEqual(self.creator.profile.balance, 500)  # refunded

    def test_non_creator_leave_refunds_individual(self):
        PokerPlayer.objects.create(
            table=self.table, user=self.joiner, seat=1,
            chips=1000, status='active', coins_invested=100,
        )
        self.client.login(username='bob', password='pass')
        response = self.client.post(f'/poker/leave/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        # Table should still be pending, not cancelled
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'pending')
        # Bob refunded
        self.joiner.profile.refresh_from_db()
        self.assertEqual(self.joiner.profile.balance, 500)
        # Bob's player row deleted
        self.assertFalse(
            PokerPlayer.objects.filter(table=self.table, user=self.joiner).exists()
        )


class PlayViewTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user('alice', password='pass')
        self.creator.profile.balance = 500
        self.creator.profile.save()
        self.other = User.objects.create_user('eve', password='pass')
        self.table = PokerTable.objects.create(
            creator=self.creator, stake=100,
        )
        PokerPlayer.objects.create(
            table=self.table, user=self.creator, seat=0,
            chips=1000, status='active', coins_invested=100,
        )

    def test_player_can_access_play(self):
        self.client.login(username='alice', password='pass')
        response = self.client.get(f'/poker/play/{self.table.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_creator'])

    def test_non_player_redirected(self):
        self.client.login(username='eve', password='pass')
        response = self.client.get(f'/poker/play/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)

    def test_play_requires_login(self):
        response = self.client.get(f'/poker/play/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)


class StartTableViewTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user('alice', password='pass')
        self.creator.profile.balance = 500
        self.creator.profile.save()
        self.table = PokerTable.objects.create(
            creator=self.creator, stake=100, min_players=2,
        )
        PokerPlayer.objects.create(
            table=self.table, user=self.creator, seat=0,
            chips=1000, status='active', coins_invested=100,
        )

    def test_start_with_insufficient_players(self):
        self.client.login(username='alice', password='pass')
        response = self.client.post(f'/poker/start/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'pending')

    def test_start_with_enough_players(self):
        bob = User.objects.create_user('bob', password='pass')
        bob.profile.balance = 500
        bob.profile.save()
        PokerPlayer.objects.create(
            table=self.table, user=bob, seat=1,
            chips=1000, status='active', coins_invested=100,
        )
        self.client.login(username='alice', password='pass')
        response = self.client.post(f'/poker/start/{self.table.pk}/')
        self.assertEqual(response.status_code, 302)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'active')
        self.assertIsNotNone(self.table.started_at)

    def test_non_creator_cannot_start(self):
        bob = User.objects.create_user('bob', password='pass')
        bob.profile.balance = 500
        bob.profile.save()
        PokerPlayer.objects.create(
            table=self.table, user=bob, seat=1,
            chips=1000, status='active', coins_invested=100,
        )
        self.client.login(username='bob', password='pass')
        response = self.client.post(f'/poker/start/{self.table.pk}/')
        self.assertEqual(response.status_code, 404)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'pending')
