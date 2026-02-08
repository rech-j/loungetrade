from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .forms import ProfileEditForm
from .models import UserProfile


class UserProfileSignalTest(TestCase):
    def test_profile_created_on_user_creation(self):
        user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')
        self.assertTrue(hasattr(user, 'profile'))
        self.assertEqual(user.profile.balance, 0)
        self.assertEqual(user.profile.display_name, 'testuser')

    def test_profile_display_name(self):
        user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')
        self.assertEqual(user.profile.get_display_name(), 'testuser')
        user.profile.display_name = 'Custom Name'
        user.profile.save()
        self.assertEqual(user.profile.get_display_name(), 'Custom Name')


class ProfileViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')

    def test_profile_requires_login(self):
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 302)

    def test_profile_accessible_when_logged_in(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 200)


class LandingPageTest(TestCase):
    def test_landing_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lounge Coin')

    def test_landing_redirects_authenticated(self):
        User.objects.create_user('testuser', 'test@test.com', 'pass1234')
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)


class NameCooldownTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')

    def test_first_name_change_allowed(self):
        form = ProfileEditForm(
            data={'display_name': 'NewName'},
            instance=self.user.profile,
        )
        self.assertTrue(form.is_valid())

    def test_name_change_within_cooldown_rejected(self):
        self.user.profile.name_changed_at = timezone.now()
        self.user.profile.save()
        form = ProfileEditForm(
            data={'display_name': 'AnotherName'},
            instance=self.user.profile,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('display_name', form.errors)

    def test_name_change_after_cooldown_allowed(self):
        self.user.profile.name_changed_at = timezone.now() - timezone.timedelta(hours=25)
        self.user.profile.save()
        form = ProfileEditForm(
            data={'display_name': 'AnotherName'},
            instance=self.user.profile,
        )
        self.assertTrue(form.is_valid())

    def test_same_name_no_cooldown_check(self):
        self.user.profile.name_changed_at = timezone.now()
        self.user.profile.save()
        form = ProfileEditForm(
            data={'display_name': 'testuser'},
            instance=self.user.profile,
        )
        self.assertTrue(form.is_valid())


class DarkModeToggleTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')
        self.client.login(username='testuser', password='pass1234')

    def test_toggle_dark_mode(self):
        self.assertFalse(self.user.profile.dark_mode)
        self.client.post('/profile/toggle-dark-mode/')
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.dark_mode)
        self.client.post('/profile/toggle-dark-mode/')
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.dark_mode)


class UserSearchTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')

    def test_search_returns_results(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/profile/search/json/?q=bo')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['users']), 1)
        self.assertEqual(data['users'][0]['username'], 'bob')

    def test_search_excludes_self(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/profile/search/json/?q=ali')
        data = response.json()
        self.assertEqual(len(data['users']), 0)

    def test_search_too_short(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/profile/search/json/?q=b')
        data = response.json()
        self.assertEqual(len(data['users']), 0)
