from django.contrib.auth.models import User
from django.test import TestCase

from .models import Notification


class NotificationModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')

    def test_create_notification(self):
        notif = Notification.objects.create(
            user=self.user,
            notif_type='coin_received',
            title='Test',
            message='Test message',
        )
        self.assertFalse(notif.is_read)

    def test_unread_count_context(self):
        Notification.objects.create(
            user=self.user,
            notif_type='coin_received',
            title='Test',
            message='Test message',
        )
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get('/profile/')
        self.assertEqual(response.context['unread_notification_count'], 1)


class NotificationViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')
        self.notif = Notification.objects.create(
            user=self.user,
            notif_type='coin_received',
            title='Test',
            message='Test message',
        )

    def test_notification_list(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get('/notifications/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test')

    def test_mark_read_requires_post(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get(f'/notifications/read/{self.notif.pk}/')
        self.assertEqual(response.status_code, 405)

    def test_mark_read_post(self):
        self.client.login(username='testuser', password='pass1234')
        self.client.post(f'/notifications/read/{self.notif.pk}/')
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_read)

    def test_mark_all_read(self):
        Notification.objects.create(
            user=self.user, notif_type='game_invite',
            title='Test2', message='msg',
        )
        self.client.login(username='testuser', password='pass1234')
        self.client.post('/notifications/read-all/')
        self.assertEqual(
            Notification.objects.filter(user=self.user, is_read=False).count(),
            0
        )

    def test_cannot_mark_other_users_notification(self):
        other = User.objects.create_user('other', 'other@test.com', 'pass1234')
        other_notif = Notification.objects.create(
            user=other, notif_type='coin_received',
            title='Other', message='msg',
        )
        self.client.login(username='testuser', password='pass1234')
        self.client.post(f'/notifications/read/{other_notif.pk}/')
        other_notif.refresh_from_db()
        self.assertFalse(other_notif.is_read)  # should remain unread
