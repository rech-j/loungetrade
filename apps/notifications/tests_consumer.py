from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User
from django.test import TransactionTestCase

from .consumers import NotificationConsumer


class NotificationConsumerTest(TransactionTestCase):
    """Tests for the NotificationConsumer WebSocket."""

    async def _create_user(self):
        return await database_sync_to_async(User.objects.create_user)(
            'testuser', 'test@test.com', 'pass1234',
        )

    def _make_communicator(self, user=None):
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), '/ws/notifications/',
        )
        communicator.scope['user'] = user or AnonymousUser()
        return communicator

    async def test_anonymous_rejected(self):
        communicator = self._make_communicator()
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_authenticated_connects(self):
        user = await self._create_user()
        communicator = self._make_communicator(user)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_new_notification_message(self):
        user = await self._create_user()
        communicator = self._make_communicator(user)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Simulate a group_send
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        await channel_layer.group_send(f'notifications_{user.pk}', {
            'type': 'new_notification',
            'notification': {
                'id': 1,
                'notif_type': 'coin_received',
                'title': 'Test',
                'message': 'Test message',
                'link': '/profile/',
                'created_at': '2026-01-01T00:00:00Z',
            },
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'new_notification')
        self.assertEqual(response['notification']['title'], 'Test')
        await communicator.disconnect()
