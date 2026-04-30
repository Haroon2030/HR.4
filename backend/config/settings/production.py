"""
إعدادات الإنتاج - Production Settings (Dokploy + PostgreSQL)
"""

import environ
from .base import *  # noqa: F401,F403

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

# ──────────────────────────────────────────────────────────────────────────────
# Core
# ──────────────────────────────────────────────────────────────────────────────
SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = env.list(
    'ALLOWED_HOSTS',
    default=['72.61.107.230', 'localhost', '127.0.0.1'],
)

CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS',
    default=[
        'http://72.61.107.230',
        'http://72.61.107.230:8082',
    ],
)

# ──────────────────────────────────────────────────────────────────────────────
# Database — PostgreSQL via DATABASE_URL
# Example: postgres://hr_user:PASSWORD@hr-hrdba-xxxx:5432/hr_db
# ──────────────────────────────────────────────────────────────────────────────
DATABASES = {
    'default': env.db('DATABASE_URL'),
}
DATABASES['default'].setdefault('CONN_MAX_AGE', 60)

# ──────────────────────────────────────────────────────────────────────────────
# Security (behind reverse proxy / Traefik in Dokploy)
# ──────────────────────────────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=False)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=False)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

# ──────────────────────────────────────────────────────────────────────────────
# CORS
# ──────────────────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=False)
CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS',
    default=[
        'http://72.61.107.230',
        'http://72.61.107.230:8082',
    ],
)
CORS_ALLOW_CREDENTIALS = True

# ──────────────────────────────────────────────────────────────────────────────
# Logging — stdout (container friendly)
# ──────────────────────────────────────────────────────────────────────────────
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
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
