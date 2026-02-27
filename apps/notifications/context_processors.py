from django.core.cache import cache


def unread_notification_count(request):
    if request.user.is_authenticated:
        cache_key = f'unread_notif_count:{request.user.pk}'
        count = cache.get(cache_key)
        if count is None:
            count = request.user.notifications.filter(is_read=False).count()
            cache.set(cache_key, count, 30)  # Cache for 30 seconds
        return {'unread_notification_count': count}
    return {'unread_notification_count': 0}
