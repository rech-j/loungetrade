import logging
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger(__name__)


def rate_limit(key_prefix, max_requests=10, window=60):
    """Simple rate limiter using Django's cache framework with atomic increments.

    Args:
        key_prefix: Unique prefix for this endpoint
        max_requests: Maximum requests allowed in window
        window: Time window in seconds
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_authenticated:
                identifier = str(request.user.pk)
            else:
                ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                ip = ip or request.META.get('REMOTE_ADDR', 'unknown')
                identifier = ip

            cache_key = f'ratelimit:{key_prefix}:{identifier}'

            # Atomic increment to prevent race conditions
            try:
                requests_made = cache.incr(cache_key)
            except ValueError:
                # Key doesn't exist yet — initialize it
                cache.set(cache_key, 1, window)
                requests_made = 1

            if requests_made > max_requests:
                logger.warning(
                    'Rate limit exceeded: key=%s identifier=%s',
                    key_prefix, identifier,
                )
                return HttpResponse(
                    'Too many requests. Please try again later.',
                    status=429,
                )
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
