from django.contrib.auth.models import User
from django.test import TestCase


class LeaderboardViewTest(TestCase):
    def test_leaderboard_accessible(self):
        response = self.client.get('/leaderboard/')
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_shows_users(self):
        user = User.objects.create_user('richuser', 'rich@test.com', 'pass1234')
        user.profile.balance = 1000
        user.profile.save()
        response = self.client.get('/leaderboard/')
        self.assertContains(response, 'richuser')
        self.assertContains(response, '1000')

    def test_leaderboard_ordered_by_balance(self):
        u1 = User.objects.create_user('poor', 'poor@test.com', 'pass1234')
        u2 = User.objects.create_user('rich', 'rich@test.com', 'pass1234')
        u1.profile.balance = 10
        u1.profile.save()
        u2.profile.balance = 500
        u2.profile.save()
        response = self.client.get('/leaderboard/')
        content = response.content.decode()
        rich_pos = content.index('rich')
        poor_pos = content.index('poor')
        self.assertLess(rich_pos, poor_pos)
