from django.contrib.auth.models import User
from django.test import TestCase

from apps.economy.services import transfer_coins


class LeaderboardViewTest(TestCase):
    def test_leaderboard_accessible(self):
        response = self.client.get('/leaderboard/')
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_accessible_when_logged_in(self):
        User.objects.create_user('testuser', 'test@test.com', 'pass1234')
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get('/leaderboard/')
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_shows_users(self):
        user = User.objects.create_user('richuser', 'rich@test.com', 'pass1234')
        user.profile.balance = 1000
        user.profile.save()
        response = self.client.get('/leaderboard/')
        self.assertContains(response, 'richuser')
        self.assertContains(response, '1,000')

    def test_leaderboard_ordered_by_balance(self):
        u1 = User.objects.create_user('pooruser', 'poor@test.com', 'pass1234')
        u2 = User.objects.create_user('richuser', 'rich@test.com', 'pass1234')
        u1.profile.balance = 10
        u1.profile.save()
        u2.profile.balance = 500
        u2.profile.save()
        response = self.client.get('/leaderboard/')
        profiles = response.context['profiles']
        self.assertEqual(profiles[0].user.username, 'richuser')
        self.assertEqual(profiles[1].user.username, 'pooruser')

    def test_leaderboard_hidden_user_excluded(self):
        visible = User.objects.create_user('visible', 'vis@test.com', 'pass1234')
        visible.profile.balance = 500
        visible.profile.save()
        hidden = User.objects.create_user('hidden', 'hid@test.com', 'pass1234')
        hidden.profile.balance = 1000
        hidden.profile.leaderboard_hidden = True
        hidden.profile.save()
        response = self.client.get('/leaderboard/')
        profiles = response.context['profiles']
        usernames = [p.user.username for p in profiles]
        self.assertIn('visible', usernames)
        self.assertNotIn('hidden', usernames)

    def test_user_rank_shown_when_authenticated(self):
        u1 = User.objects.create_user('topuser', 'top@test.com', 'pass1234')
        u1.profile.balance = 1000
        u1.profile.save()
        u2 = User.objects.create_user('miduser', 'mid@test.com', 'pass1234')
        u2.profile.balance = 500
        u2.profile.save()
        self.client.login(username='miduser', password='pass1234')
        response = self.client.get('/leaderboard/')
        self.assertEqual(response.context['user_rank'], 2)

    def test_24h_delta_calculated(self):
        alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        alice.profile.balance = 200
        alice.profile.save()
        bob.profile.balance = 100
        bob.profile.save()
        transfer_coins(alice, bob, 50, note='test')
        alice.profile.refresh_from_db()
        bob.profile.refresh_from_db()
        response = self.client.get('/leaderboard/')
        profiles = response.context['profiles']
        deltas = {p.user.username: p.delta_24h for p in profiles}
        self.assertEqual(deltas['alice'], -50)
        self.assertEqual(deltas['bob'], 50)
