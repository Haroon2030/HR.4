"""
إعدادات الإنتاج - Production Settings
"""

from .base import *
from decouple import config

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='72.61.107.230,localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# ══════════════════════════════════════════════════════════════════════════════
# Database - MySQL/PostgreSQL for Production
# ══════════════════════════════════════════════════════════════════════════════

DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.mysql'),
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

# ══════════════════════════════════════════════════════════════════════════════
# Security Settings
# ══════════════════════════════════════════════════════════════════════════════

SECURE_SSL_REDIRECT = False  # Handled by reverse proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = False  # Set to True when using HTTPS
CSRF_COOKIE_SECURE = False  # Set to True when using HTTPS
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
# SECURE_HSTS_SECONDS = 31536000  # Enable when using HTTPS
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

# ══════════════════════════════════════════════════════════════════════════════
# CORS - Restricted origins
# ══════════════════════════════════════════════════════════════════════════════

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'http://72.61.107.230:8096',
    'http://72.61.107.230',
    'http://localhost:5173',
    'http://localhost:8096',
    'http://127.0.0.1:5173',
    'http://127.0.0.1:8096',
]
CORS_ALLOW_CREDENTIALS = True

# ══════════════════════════════════════════════════════════════════════════════
# REST Framework - Production Settings
# ══════════════════════════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'config.pagination.CustomPagination',
    'PAGE_SIZE': 8,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'ERROR',
    },
}
