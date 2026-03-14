from django.contrib.auth.models import User
from django.test import TestCase

from apps.chess.models import ChessGame
from apps.notifications.models import Notification


class ChessLobbyViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')

    def test_lobby_requires_login(self):
        response = self.client.get('/chess/')
        self.assertEqual(response.status_code, 302)

    def test_lobby_accessible_when_logged_in(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get('/chess/')
        self.assertEqual(response.status_code, 200)


class CreateChessGameTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()

    def _post(self, **kwargs):
        defaults = {'opponent_username': 'bob', 'stake': 50, 'side': 'white'}
        defaults.update(kwargs)
        return self.client.post('/chess/challenge/', defaults)

    def test_create_game_success(self):
        self.client.login(username='alice', password='pass1234')
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ChessGame.objects.filter(creator=self.alice, opponent=self.bob).exists())

    def test_create_game_sends_notification(self):
        self.client.login(username='alice', password='pass1234')
        self._post()
        self.assertEqual(
            Notification.objects.filter(user=self.bob, notif_type='game_invite').count(), 1
        )

    def test_cannot_challenge_self(self):
        self.client.login(username='alice', password='pass1234')
        self._post(opponent_username='alice')
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_insufficient_balance(self):
        self.client.login(username='alice', password='pass1234')
        self._post(stake=500)
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_duplicate_pending_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self._post()
        self._post()
        self.assertEqual(ChessGame.objects.count(), 1)

    def test_zero_stake_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self._post(stake=0)
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_negative_stake_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self._post(stake=-100)
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_stake_above_max_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self._post(stake=99999)
        self.assertEqual(ChessGame.objects.count(), 0)


class ChessPlayViewAccessTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()
        self.game = ChessGame.objects.create(creator=self.alice, opponent=self.bob, stake=50)

    def test_creator_can_access_play(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get(f'/chess/play/{self.game.pk}/')
        self.assertEqual(response.status_code, 200)

    def test_opponent_can_access_play(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.get(f'/chess/play/{self.game.pk}/')
        self.assertEqual(response.status_code, 200)

    def test_non_participant_redirected(self):
        self.client.login(username='eve', password='pass1234')
        response = self.client.get(f'/chess/play/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)


class DeclineChessGameTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()
        self.game = ChessGame.objects.create(creator=self.alice, opponent=self.bob, stake=50)

    def test_opponent_can_decline(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/chess/decline/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'cancelled')

    def test_creator_cannot_decline(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/chess/decline/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_non_participant_cannot_decline(self):
        self.client.login(username='eve', password='pass1234')
        response = self.client.post(f'/chess/decline/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_cannot_decline_non_pending(self):
        self.game.status = 'active'
        self.game.save()
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/chess/decline/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)


class CancelChessGameTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()
        self.game = ChessGame.objects.create(creator=self.alice, opponent=self.bob, stake=50)

    def test_creator_can_cancel(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/chess/cancel/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'cancelled')

    def test_opponent_cannot_cancel(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/chess/cancel/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_cannot_cancel_active_game(self):
        self.game.status = 'active'
        self.game.save()
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/chess/cancel/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)
