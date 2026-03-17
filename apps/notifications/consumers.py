import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """Lightweight WebSocket consumer for real-time notification delivery."""

    async def connect(self):
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        self.group_name = f'notifications_{self.user.pk}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def new_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_notification',
            'notification': event['notification'],
        }))

    async def notification_read(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification_read',
            'id': event['id'],
        }))

    async def all_notifications_read(self, event):
        await self.send(text_data=json.dumps({
            'type': 'all_notifications_read',
        }))

    async def notification_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification_deleted',
            'id': event['id'],
        }))
