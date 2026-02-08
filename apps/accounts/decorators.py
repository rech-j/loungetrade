import time
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse


def rate_limit(key_prefix, max_requests=10, window=60):
    """Simple rate limiter using Django's cache framework.

    Args:
        key_prefix: Unique prefix for this endpoint
        max_requests: Maximum requests allowed in window
        window: Time window in seconds
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_authenticated:
                cache_key = f'ratelimit:{key_prefix}:{request.user.pk}'
            else:
                ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                ip = ip or request.META.get('REMOTE_ADDR', 'unknown')
                cache_key = f'ratelimit:{key_prefix}:{ip}'

            requests_made = cache.get(cache_key, 0)
            if requests_made >= max_requests:
                return HttpResponse(
                    'Too many requests. Please try again later.',
                    status=429,
                )
            cache.set(cache_key, requests_made + 1, window)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
