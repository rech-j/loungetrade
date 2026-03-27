"""Test settings — mirrors production security settings with CI database credentials.

Used by CI (GitHub Actions) so tests exercise the same middleware, security
headers, and password hashers as production, while using the CI PostgreSQL
service for the database.
"""

import os

from .base import *  # noqa: F401, F403

DEBUG = False
SECRET_KEY = 'test-secret-key-not-for-production'

ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'loungecoin_test'),
        'USER': os.environ.get('DB_USER', 'loungecoin'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'loungecoin'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Match production security settings so tests catch misconfigurations.
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = False  # Tests use HTTP, not HTTPS.
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SECURE_SSL_REDIRECT = False  # No TLS in CI.

# Console email for test output.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Faster password hashing in tests.
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]
