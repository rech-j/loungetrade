import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403

DEBUG = False

# Override SECRET_KEY - must be set in production
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY environment variable is required in production.')

# Validate other required env vars
_REQUIRED_ENV_VARS = ['DB_PASSWORD', 'BREVO_API_KEY', 'REDIS_URL']
_missing = [var for var in _REQUIRED_ENV_VARS if not os.environ.get(var)]
if _missing:
    raise ImproperlyConfigured(f'Missing required environment variables: {", ".join(_missing)}')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'loungecoin.trade').split(',')
ADMIN_URL = os.environ.get('DJANGO_ADMIN_URL', 'admin/')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'loungecoin'),
        'USER': os.environ.get('DB_USER', 'loungecoin'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        # Persistent connections - avoids reconnecting on every request.
        'CONN_MAX_AGE': 60,
        # Guard against runaway queries; abort after 5 seconds.
        'OPTIONS': {
            'options': '-c statement_timeout=5000',
        },
    }
}

# Security settings
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'  # 'Strict' breaks cross-site OAuth callbacks (Google redirect loses session state)
CSRF_COOKIE_SAMESITE = 'Lax'   # 'Strict' breaks cross-site OAuth callbacks
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 86400  # 24 hours
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = ['https://loungecoin.trade', 'https://www.loungecoin.trade']

# Gunicorn on a Unix socket sets REMOTE_ADDR to "" (no IP for socket connections).
# Tell allauth to read the real client IP from the X-Real-IP header that Nginx sets.
ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "X-Real-IP"

# Lock WebSocket CSP to this domain only (avoids the broad wss:/ws: wildcard).
CSP_WS_ORIGIN = 'wss://loungecoin.trade'

# allauth: use HTTPS in email links (password reset, etc.)
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'

# Email - Brevo transactional API via django-anymail (uses HTTPS, no SMTP port needed)
EMAIL_BACKEND = 'anymail.backends.brevo.EmailBackend'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@loungecoin.trade')
ANYMAIL = {
    'BREVO_API_KEY': os.environ.get('BREVO_API_KEY', ''),
}

# Use Redis channel layer in production
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')],
        },
    },
}

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.environ.get('DJANGO_LOG_FILE', '/var/log/loungecoin/django.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB per file
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        # Captures Django's internal security events (SuspiciousOperation, etc.)
        'django.security': {
            'handlers': ['file'],
            'level': 'WARNING',
            'propagate': True,
        },
        # Captures 4xx/5xx request errors
        'django.request': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
