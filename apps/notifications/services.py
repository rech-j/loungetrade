import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache

from .models import Notification

logger = logging.getLogger(__name__)


def send_notification(user, notif_type, title, message, link=''):
    """Create a notification and push it via WebSocket."""
    notif = Notification.objects.create(
        user=user,
        notif_type=notif_type,
        title=title,
        message=message,
        link=link,
    )

    # Invalidate cached unread count
    cache.delete(f'unread_notif_count:{user.pk}')

    # Push to WebSocket group
    _ws_send(user.pk, {
        'type': 'new_notification',
        'notification': {
            'id': notif.pk,
            'notif_type': notif.notif_type,
            'title': notif.title,
            'message': notif.message,
            'link': notif.link,
            'created_at': notif.created_at.isoformat(),
        },
    })

    return notif


def _ws_notify_read(user_id, pk):
    """Notify all tabs that a notification was marked read."""
    cache.delete(f'unread_notif_count:{user_id}')
    _ws_send(user_id, {
        'type': 'notification_read',
        'id': pk,
    })


def _ws_notify_deleted(user_id, pk):
    """Notify all tabs that a notification was deleted."""
    cache.delete(f'unread_notif_count:{user_id}')
    _ws_send(user_id, {
        'type': 'notification_deleted',
        'id': pk,
    })


def _ws_notify_all_read(user_id):
    """Notify all tabs that all notifications were marked read."""
    cache.delete(f'unread_notif_count:{user_id}')
    _ws_send(user_id, {
        'type': 'all_notifications_read',
    })


def _ws_send(user_id, message):
    """Send a message to the user's notification WebSocket group."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'notifications_{user_id}',
                message,
            )
    except Exception:
        logger.debug('Could not send WS notification to user %s', user_id, exc_info=True)
