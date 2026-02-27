from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase


class RateLimitAuthenticatedTest(TestCase):
    """Tests for the rate_limit decorator with authenticated users."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 50000
        self.alice.profile.save()
        self.bob.profile.balance = 50000
        self.bob.profile.save()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_requests_under_limit_allowed(self):
        """Requests under the rate limit should succeed normally."""
        self.client.login(username='alice', password='pass1234')
        for _ in range(10):
            response = self.client.post('/games/challenge/', {
                'opponent_username': 'bob',
                'stake': 10,
                'choice': 'heads',
            })
            # Should be 302 redirect (success or validation), not 429
            self.assertNotEqual(response.status_code, 429)

    def test_requests_over_limit_return_429(self):
        """Requests exceeding the rate limit should return 429."""
        self.client.login(username='alice', password='pass1234')
        # The create_challenge view has max_requests=10, window=60
        for _ in range(10):
            self.client.post('/games/challenge/', {
                'opponent_username': 'bob',
                'stake': 10,
                'choice': 'heads',
            })

        # The 11th request should be rate limited
        response = self.client.post('/games/challenge/', {
            'opponent_username': 'bob',
            'stake': 10,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 429)

    def test_tracks_by_user_id_for_authenticated(self):
        """Different authenticated users should have separate rate limit counters."""
        self.client.login(username='alice', password='pass1234')
        # Use up Alice's rate limit
        for _ in range(10):
            self.client.post('/games/challenge/', {
                'opponent_username': 'bob',
                'stake': 10,
                'choice': 'heads',
            })
        # Alice should be rate limited
        response = self.client.post('/games/challenge/', {
            'opponent_username': 'bob',
            'stake': 10,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 429)

        # Bob should NOT be rate limited (separate counter)
        self.client.logout()
        self.client.login(username='bob', password='pass1234')
        response = self.client.post('/games/challenge/', {
            'opponent_username': 'alice',
            'stake': 10,
            'choice': 'heads',
        })
        self.assertNotEqual(response.status_code, 429)

    def test_rate_limit_resets_after_cache_clear(self):
        """Rate limit should reset when the cache is cleared."""
        self.client.login(username='alice', password='pass1234')
        # Exhaust rate limit
        for _ in range(10):
            self.client.post('/games/challenge/', {
                'opponent_username': 'bob',
                'stake': 10,
                'choice': 'heads',
            })
        # Confirm rate limited
        response = self.client.post('/games/challenge/', {
            'opponent_username': 'bob',
            'stake': 10,
            'choice': 'heads',
        })
        self.assertEqual(response.status_code, 429)

        # Clear cache to simulate window expiry
        cache.clear()

        # Should be allowed again
        response = self.client.post('/games/challenge/', {
            'opponent_username': 'bob',
            'stake': 10,
            'choice': 'heads',
        })
        self.assertNotEqual(response.status_code, 429)


class RateLimitAnonymousTest(TestCase):
    """Tests for the rate_limit decorator with anonymous users."""

    def setUp(self):
        # create_challenge requires login, so anonymous users get redirected
        # before the rate limiter. We test the IP-tracking logic by verifying
        # the cache key is based on IP through the decorator's internal logic.
        # Since the rate-limited views in this project all require @login_required,
        # we test the decorator directly with a minimal view.
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_tracks_by_ip_for_anonymous(self):
        """Anonymous users should be tracked by IP address in the rate limiter.

        We test this by directly invoking the decorator on a simple view
        and confirming the cache key uses the IP.
        """
        from django.http import HttpResponse
        from django.test import RequestFactory

        from apps.accounts.decorators import rate_limit

        @rate_limit('test_anon', max_requests=2, window=60)
        def dummy_view(request):
            return HttpResponse('ok')

        factory = RequestFactory()

        # Simulate requests from IP 10.0.0.1
        request = factory.get('/fake/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False, 'is_anonymous': True})()
        request.META['REMOTE_ADDR'] = '10.0.0.1'

        # First two requests should pass
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

        # Third request from same IP should be rate limited
        response = dummy_view(request)
        self.assertEqual(response.status_code, 429)

        # Request from different IP should still pass
        request2 = factory.get('/fake/')
        request2.user = type('AnonymousUser', (), {'is_authenticated': False, 'is_anonymous': True})()
        request2.META['REMOTE_ADDR'] = '10.0.0.2'
        response = dummy_view(request2)
        self.assertEqual(response.status_code, 200)

    def test_x_forwarded_for_used_for_ip(self):
        """When HTTP_X_FORWARDED_FOR is present, the first IP should be used."""
        from django.http import HttpResponse
        from django.test import RequestFactory

        from apps.accounts.decorators import rate_limit

        @rate_limit('test_xff', max_requests=1, window=60)
        def dummy_view(request):
            return HttpResponse('ok')

        factory = RequestFactory()
        request = factory.get('/fake/', HTTP_X_FORWARDED_FOR='203.0.113.5, 10.0.0.1')
        request.user = type('AnonymousUser', (), {'is_authenticated': False, 'is_anonymous': True})()

        # First request passes
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

        # Second from same forwarded IP is limited
        response = dummy_view(request)
        self.assertEqual(response.status_code, 429)

        # Different forwarded IP is not limited
        request2 = factory.get('/fake/', HTTP_X_FORWARDED_FOR='198.51.100.1, 10.0.0.1')
        request2.user = type('AnonymousUser', (), {'is_authenticated': False, 'is_anonymous': True})()
        response = dummy_view(request2)
        self.assertEqual(response.status_code, 200)
