from django.contrib.auth.models import User
from django.test import TestCase

from apps.economy.services import InsufficientFunds, game_transfer
from apps.coinflip.models import CoinFlipChallenge
from apps.notifications.models import Notification


class CoinFlipChallengeTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()

    def test_create_challenge(self):
        challenge = CoinFlipChallenge.objects.create(
            challenger=self.alice,
            opponent=self.bob,
            stake=50,
            challenger_choice='heads',
        )
        self.assertEqual(challenge.status, 'pending')
        self.assertIsNone(challenge.winner)

    def test_game_transfer(self):
        game_transfer(self.alice, self.bob, 50)
        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 150)
        self.assertEqual(self.bob.profile.balance, 50)

    def test_game_transfer_insufficient(self):
        with self.assertRaises(InsufficientFunds):
            game_transfer(self.alice, self.bob, 200)


class CoinFlipLobbyViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')

    def test_lobby_requires_login(self):
        response = self.client.get('/coinflip/')
        self.assertEqual(response.status_code, 302)

    def test_lobby_accessible_when_logged_in(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get('/coinflip/')
        self.assertEqual(response.status_code, 200)


class CreateChallengeViewTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()

    def test_create_challenge_success(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 50,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CoinFlipChallenge.objects.filter(
            challenger=self.alice, opponent=self.bob
        ).exists())

    def test_challenge_sends_notification(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 50,
            'choice': 'heads',
        })
        self.assertEqual(
            Notification.objects.filter(user=self.bob, notif_type='game_invite').count(),
            1
        )

    def test_cannot_challenge_self(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'alice',
            'stake': 50,
            'choice': 'heads',
        })
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)

    def test_invalid_choice_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 50,
            'choice': 'invalid',
        })
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)

    def test_insufficient_balance(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 500,
            'choice': 'heads',
        })
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)

    def test_duplicate_pending_challenge_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 10,
            'choice': 'heads',
        })
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 10,
            'choice': 'tails',
        })
        self.assertEqual(CoinFlipChallenge.objects.count(), 1)

    def test_get_request_redirects(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/coinflip/challenge/')
        self.assertEqual(response.status_code, 302)
