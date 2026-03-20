from django.contrib.auth.models import User
from django.test import TestCase

from apps.coinflip.models import CoinFlipChallenge
from apps.notifications.models import Notification


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
        self.assertRedirects(response, f'/coinflip/play/{CoinFlipChallenge.objects.first().pk}/')
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
