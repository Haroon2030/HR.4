"""
إعدادات التطوير - Development Settings
"""

import environ
from .base import *

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-dev-key-change-in-production-!@#$%^&*()'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# ══════════════════════════════════════════════════════════════════════════════
# Database - DATABASE_URL from .env (Neon Postgres) or fallback to SQLite
# ══════════════════════════════════════════════════════════════════════════════

if env('DATABASE_URL', default=''):
    DATABASES = {'default': env.db('DATABASE_URL')}
    DATABASES['default'].setdefault('CONN_MAX_AGE', 60)
    DATABASES['default'].setdefault('DISABLE_SERVER_SIDE_CURSORS', True)
    if DATABASES['default'].get('ENGINE', '').endswith('postgresql'):
        _opts = DATABASES['default'].setdefault('OPTIONS', {})
        _opts.setdefault('sslmode', env('DB_SSLMODE', default='require'))
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ══════════════════════════════════════════════════════════════════════════════
# CORS - Allow all origins in development
# ══════════════════════════════════════════════════════════════════════════════

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# وكيل البصمة — السماح للمفتاح العام بقائمة الأجهزة في التطوير
AGENT_GLOBAL_KEY_LIST_DEVICES = True

# ══════════════════════════════════════════════════════════════════════════════
# REST Framework — يُورث من base.py (JWT، throttling، spectacular، معالج الأخطاء)
# تخصيص التطوير فقط: ترقيم أوضح للقوائم عند التجربة اليدوية
# ══════════════════════════════════════════════════════════════════════════════

REST_FRAMEWORK['DEFAULT_PAGINATION_CLASS'] = 'rest_framework.pagination.PageNumberPagination'
REST_FRAMEWORK['PAGE_SIZE'] = 20

# ══════════════════════════════════════════════════════════════════════════════
# Debug Toolbar (optional)
# ══════════════════════════════════════════════════════════════════════════════

# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']

# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
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

# ══════════════════════════════════════════════════════════════════════════════
# Email
# إعدادات البريد الإلكتروني مُعرّفة في base.py وتُقرأ من .env
# في التطوير: إذا EMAIL_HOST غير مُعدّ، يُستخدم console backend تلقائياً
# ══════════════════════════════════════════════════════════════════════════════
