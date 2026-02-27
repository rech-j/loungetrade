from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from apps.coinflip.models import CoinFlipChallenge


class UnauthenticatedAccessTest(TestCase):
    """Ensure unauthenticated users cannot access coin flip endpoints."""

    def test_unauthenticated_cannot_access_lobby(self):
        response = self.client.get('/coinflip/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_unauthenticated_cannot_create_challenge(self):
        response = self.client.post('/coinflip/challenge/', {
            'opponent_username': 'someone',
            'stake': 10,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)

    def test_unauthenticated_cannot_access_play(self):
        alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        challenge = CoinFlipChallenge.objects.create(
            challenger=alice, opponent=bob, stake=10, challenger_choice='heads',
        )
        response = self.client.get(f'/coinflip/play/{challenge.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_unauthenticated_cannot_decline_challenge(self):
        alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        challenge = CoinFlipChallenge.objects.create(
            challenger=alice, opponent=bob, stake=10, challenger_choice='heads',
        )
        response = self.client.post(f'/coinflip/decline/{challenge.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, 'pending')


class SelfChallengeTest(TestCase):
    """Ensure a user cannot challenge themselves."""

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.alice.profile.balance = 1000
        self.alice.profile.save()

    def test_cannot_challenge_self(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post('/coinflip/challenge/', {
            'opponent_username': 'alice',
            'stake': 50,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)


class GameAccessControlTest(TestCase):
    """Ensure users can only access games they are part of."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.charlie = User.objects.create_user('charlie', 'charlie@test.com', 'pass1234')
        for user in [self.alice, self.bob, self.charlie]:
            user.profile.balance = 1000
            user.profile.save()
        self.challenge = CoinFlipChallenge.objects.create(
            challenger=self.alice,
            opponent=self.bob,
            stake=50,
            challenger_choice='heads',
        )

    def test_non_participant_cannot_access_game(self):
        self.client.login(username='charlie', password='pass1234')
        response = self.client.get(f'/coinflip/play/{self.challenge.pk}/')
        # Should redirect to lobby with error message
        self.assertEqual(response.status_code, 302)

    def test_challenger_can_access_game(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get(f'/coinflip/play/{self.challenge.pk}/')
        self.assertEqual(response.status_code, 200)

    def test_opponent_can_access_game(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.get(f'/coinflip/play/{self.challenge.pk}/')
        self.assertEqual(response.status_code, 200)


class MaxStakeValidationTest(TestCase):
    """Test that stake validation enforces the maximum."""

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 999999
        self.alice.profile.save()
        self.bob.profile.balance = 999999
        self.bob.profile.save()

    def test_stake_above_max_rejected(self):
        """Stake exceeding MAX_GAME_STAKE (default 10000) should be rejected."""
        self.client.login(username='alice', password='pass1234')
        response = self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 10001,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)

    def test_stake_at_max_accepted(self):
        """Stake exactly at MAX_GAME_STAKE should be accepted."""
        self.client.login(username='alice', password='pass1234')
        response = self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 10000,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CoinFlipChallenge.objects.count(), 1)

    def test_zero_stake_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 0,
            'choice': 'heads',
        })
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)

    def test_negative_stake_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': -100,
            'choice': 'heads',
        })
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)

    def test_non_numeric_stake_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 'abc',
            'choice': 'heads',
        })
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)


class DeclineChallengeSecurityTest(TestCase):
    """Test that only the opponent can decline a challenge."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.charlie = User.objects.create_user('charlie', 'charlie@test.com', 'pass1234')
        for user in [self.alice, self.bob, self.charlie]:
            user.profile.balance = 1000
            user.profile.save()
        self.challenge = CoinFlipChallenge.objects.create(
            challenger=self.alice,
            opponent=self.bob,
            stake=50,
            challenger_choice='heads',
        )

    def test_opponent_can_decline(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/coinflip/decline/{self.challenge.pk}/')
        self.assertEqual(response.status_code, 302)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, 'declined')

    def test_challenger_cannot_decline(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/coinflip/decline/{self.challenge.pk}/')
        # Should be 404 since get_object_or_404 filters by opponent=request.user
        self.assertEqual(response.status_code, 404)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, 'pending')

    def test_non_participant_cannot_decline(self):
        self.client.login(username='charlie', password='pass1234')
        response = self.client.post(f'/coinflip/decline/{self.challenge.pk}/')
        self.assertEqual(response.status_code, 404)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, 'pending')

    def test_decline_get_request_redirects(self):
        """GET requests to decline should redirect, not perform the action."""
        self.client.login(username='bob', password='pass1234')
        response = self.client.get(f'/coinflip/decline/{self.challenge.pk}/')
        self.assertEqual(response.status_code, 302)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, 'pending')

    def test_decline_already_completed_challenge_fails(self):
        """Cannot decline a challenge that is no longer pending."""
        self.challenge.status = 'completed'
        self.challenge.save()
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/coinflip/decline/{self.challenge.pk}/')
        # get_object_or_404 filters by status='pending', so should 404
        self.assertEqual(response.status_code, 404)


class CSRFProtectionTest(TestCase):
    """Test that CSRF protection is enforced on state-changing endpoints."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 1000
        self.alice.profile.save()
        self.bob.profile.balance = 1000
        self.bob.profile.save()

    def test_create_challenge_csrf_enforced(self):
        """POST to create_challenge without CSRF token should be rejected."""
        self.client.login(username='alice', password='pass1234')
        # enforce_csrf_checks=True makes the test client enforce CSRF
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.login(username='alice', password='pass1234')
        response = csrf_client.post('/coinflip/challenge/', {
            'opponent_username': 'bob',
            'stake': 50,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CoinFlipChallenge.objects.count(), 0)

    def test_decline_challenge_csrf_enforced(self):
        """POST to decline_challenge without CSRF token should be rejected."""
        challenge = CoinFlipChallenge.objects.create(
            challenger=self.alice, opponent=self.bob,
            stake=50, challenger_choice='heads',
        )
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.login(username='bob', password='pass1234')
        response = csrf_client.post(f'/coinflip/decline/{challenge.pk}/')
        self.assertEqual(response.status_code, 403)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, 'pending')
