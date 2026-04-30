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
# Database — PostgreSQL
# Supports two styles:
#   1) DATABASE_URL=postgres://user:pass@host:5432/dbname  (preferred)
#   2) DB_ENGINE / DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT
# ──────────────────────────────────────────────────────────────────────────────
if env('DATABASE_URL', default=''):
    DATABASES = {
        'default': env.db('DATABASE_URL'),
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': env('DB_ENGINE', default='django.db.backends.postgresql'),
            'NAME': env('DB_NAME'),
            'USER': env('DB_USER'),
            'PASSWORD': env('DB_PASSWORD'),
            'HOST': env('DB_HOST'),
            'PORT': env('DB_PORT', default='5432'),
        }
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

# ──────────────────────────────────────────────────────────────────────────────
# Cloudflare R2 (S3-compatible) media storage
# Files organized as:  HR/<operation>/<year>/<filename>
# ──────────────────────────────────────────────────────────────────────────────
USE_R2 = env.bool('USE_R2', default=False)

if USE_R2:
    AWS_ACCESS_KEY_ID = env('R2_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('R2_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env('R2_BUCKET_NAME', default='erphr')
    AWS_S3_ENDPOINT_URL = env('R2_ENDPOINT_URL')
    AWS_S3_REGION_NAME = env('R2_REGION', default='auto')
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_ADDRESSING_STYLE = 'virtual'

    # Optional public custom domain (e.g. media.yourdomain.com).
    # If empty, MEDIA_URL falls back to the bucket endpoint.
    AWS_S3_CUSTOM_DOMAIN = env('R2_PUBLIC_DOMAIN', default='')

    STORAGES = {
        'default': {
            'BACKEND': 'apps.core.storages.HRMediaStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    else:
        MEDIA_URL = f'{AWS_S3_ENDPOINT_URL.rstrip("/")}/{AWS_STORAGE_BUCKET_NAME}/'

