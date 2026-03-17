from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from .models import Notification
from .services import send_notification


class NotificationModelTest(TestCase):
    def setUp(self):
        cache.clear()
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


class SendNotificationTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')

    @patch('apps.notifications.services.get_channel_layer')
    def test_send_notification_creates_row(self, mock_channel_layer):
        mock_channel_layer.return_value = None  # No channel layer in test
        notif = send_notification(
            self.user, 'coin_received', 'Test Title', 'Test message', link='/profile/',
        )
        self.assertEqual(notif.user, self.user)
        self.assertEqual(notif.notif_type, 'coin_received')
        self.assertEqual(notif.title, 'Test Title')
        self.assertEqual(notif.link, '/profile/')
        self.assertFalse(notif.is_read)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    @patch('apps.notifications.services.get_channel_layer')
    def test_send_notification_invalidates_cache(self, mock_channel_layer):
        mock_channel_layer.return_value = None
        cache.set(f'unread_notif_count:{self.user.pk}', 5)
        send_notification(self.user, 'game_invite', 'Test', 'msg')
        self.assertIsNone(cache.get(f'unread_notif_count:{self.user.pk}'))


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

    def test_mark_read_htmx_returns_partial(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.post(
            f'/notifications/read/{self.notif.pk}/',
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'notif-row')

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

    def test_delete_notification(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.post(f'/notifications/delete/{self.notif.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Notification.objects.filter(pk=self.notif.pk).exists())

    def test_delete_notification_htmx(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.post(
            f'/notifications/delete/{self.notif.pk}/',
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')
        self.assertFalse(Notification.objects.filter(pk=self.notif.pk).exists())

    def test_cannot_delete_other_users_notification(self):
        other = User.objects.create_user('other', 'other@test.com', 'pass1234')
        other_notif = Notification.objects.create(
            user=other, notif_type='coin_received',
            title='Other', message='msg',
        )
        self.client.login(username='testuser', password='pass1234')
        response = self.client.post(f'/notifications/delete/{other_notif.pk}/')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Notification.objects.filter(pk=other_notif.pk).exists())

    def test_delete_requires_post(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get(f'/notifications/delete/{self.notif.pk}/')
        self.assertEqual(response.status_code, 405)

    def test_pagination(self):
        # Create 25 notifications (1 already exists from setUp)
        for i in range(24):
            Notification.objects.create(
                user=self.user, notif_type='coin_received',
                title=f'Notif {i}', message='msg',
            )
        self.client.login(username='testuser', password='pass1234')
        # Page 1 should have 20 notifications
        response = self.client.get('/notifications/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['page_obj'].object_list), 20)
        # Page 2 should have 5
        response = self.client.get('/notifications/?page=2')
        self.assertEqual(len(response.context['page_obj'].object_list), 5)


class GameActivityTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')
        self.client.login(username='testuser', password='pass1234')

    def test_get_active_games_includes_poker(self):
        from apps.notifications.views import _get_active_games
        from apps.poker.models import PokerPlayer, PokerTable

        table = PokerTable.objects.create(
            creator=self.user, stake=100, status='active',
        )
        PokerPlayer.objects.create(
            table=table, user=self.user, seat=0, chips=1000, status='active',
        )
        chess_games, coinflip_games, poker_tables = _get_active_games(self.user)
        self.assertEqual(len(poker_tables), 1)
        self.assertEqual(poker_tables[0].pk, table.pk)
