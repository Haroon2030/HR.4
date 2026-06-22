"""
إعدادات بيئة الإنتاج — Production Settings
=============================================
هذا الملف يحتوي على إعدادات سيرفر الإنتاج الذي يعمل عبر Dokploy.
يعتمد على قاعدة بيانات PostgreSQL (Neon) وتخزين ملفات عبر Cloudflare R2.

⚠️ جميع القيم الحساسة (مفاتيح، كلمات مرور) تُقرأ من ملف .env — لا تكتبها هنا مباشرة!
"""

import environ
from .base import *  # noqa: F401,F403

# ── قراءة متغيرات البيئة من ملف .env ──
env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

# ══════════════════════════════════════════════════════════════════════════════
# الإعدادات الأساسية
# ══════════════════════════════════════════════════════════════════════════════

# المفتاح السري — يُقرأ من .env (إجباري)
# إن احتوى $ ضعه بين علامتي اقتباس مفردة '...' حتى لا يقطعه Docker/Compose
SECRET_KEY = env('SECRET_KEY').strip().strip('"').strip("'")

# وضع التصحيح — يجب أن يكون False في الإنتاج دائماً
DEBUG = env.bool('DEBUG', default=False)

# النطاقات/العناوين المسموح لها بالوصول للسيرفر
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# النطاقات الموثوقة لحماية CSRF (مطلوبة لنماذج POST) — حدّد https:// في .env
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# ══════════════════════════════════════════════════════════════════════════════
# قاعدة البيانات — PostgreSQL عبر Neon (خدمة سحابية)
# صيغة الرابط: postgresql://user:pass@host/dbname?sslmode=require
# ══════════════════════════════════════════════════════════════════════════════
DATABASES = {
    'default': env.db('DATABASE_URL'),
}

# الاتصال المستمر — يعيد استخدام الاتصال بدل فتح جديد لكل طلب (توفير ~200ms)
DATABASES['default'].setdefault('CONN_MAX_AGE', env.int('CONN_MAX_AGE', default=600))

# فحص صحة الاتصال قبل إعادة استخدامه (Django 4.1+) — يمنع أخطاء الاتصال المنتهي
DATABASES['default'].setdefault('CONN_HEALTH_CHECKS', True)

# إعدادات التوافق مع Neon / PgBouncer (PostgreSQL فقط — لا تُمرَّر لـ SQLite في CI)
_db_engine = DATABASES['default'].get('ENGINE', '')
if 'postgresql' in _db_engine:
    DATABASES['default'].setdefault('DISABLE_SERVER_SIDE_CURSORS', True)
    _db_options = DATABASES['default'].setdefault('OPTIONS', {})
    _db_options.setdefault('sslmode', env('DB_SSLMODE', default='require'))
    _db_options.setdefault('connect_timeout', 10)
    _db_options.setdefault('keepalives', 1)
    _db_options.setdefault('keepalives_idle', 30)
    _db_options.setdefault('keepalives_interval', 10)
    _db_options.setdefault('keepalives_count', 5)

# ══════════════════════════════════════════════════════════════════════════════
# التخزين المؤقت (Cache)
# - بدون REDIS_URL: LocMemCache (عملية واحدة / worker واحد)
# - مع REDIS_URL: Redis — مُوصى به عند أكثر من worker Gunicorn أو عدة نُسخ
# ══════════════════════════════════════════════════════════════════════════════
_REDIS_URL = env('REDIS_URL', default='').strip()
if _REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': _REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
            'KEY_PREFIX': env('REDIS_KEY_PREFIX', default='hr'),
            'TIMEOUT': env.int('REDIS_CACHE_TIMEOUT', default=300),
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'hr-default',
            'TIMEOUT': 300,
            'OPTIONS': {'MAX_ENTRIES': 5000},
        }
    }
    # LocMemCache مع عدة workers Gunicorn لا يشارك الذاكرة بين العمليات —
    # يُفضّل REDIS_URL عند التوسع؛ التحذير يُطبع من entrypoint.sh عند الإقلاع.

# استخدام التخزين المؤقت للجلسات أيضاً — يقلل الضغط على قاعدة البيانات
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

# ══════════════════════════════════════════════════════════════════════════════
# الأمان — السيرفر خلف Reverse Proxy (Traefik / Nginx / Dokploy)
# ══════════════════════════════════════════════════════════════════════════════


def _validate_production_secret_key(key: str) -> None:
    from django.core.exceptions import ImproperlyConfigured

    _gen_hint = (
        'python -c "from django.core.management.utils import get_random_secret_key; '
        'print(get_random_secret_key())"'
    )
    if not key or key.startswith('django-insecure'):
        raise ImproperlyConfigured(
            f'SECRET_KEY غير آمن في .env. أنشئ مفتاحاً عشوائياً (يُفضّل 50+ حرفاً): {_gen_hint}'
        )
    # حد أدنى 32 حرفاً (متوافق مع Django) — يُفضّل 50+ في الإنتاج الجديد
    if len(key) < 32:
        raise ImproperlyConfigured(
            f'SECRET_KEY قصير جداً ({len(key)} حرفاً) — غالباً بسبب رمز $ في .env بدون علامات اقتباس. '
            f'استخدم مفتاحاً بدون $ أو ضعه بين \'...\' . 32 حرفاً كحد أدنى. {_gen_hint}'
        )
    if len(key) < 50 and len(set(key)) < 5:
        raise ImproperlyConfigured(
            f'SECRET_KEY ضعيف (تنوع أحرف قليل). استخدم مفتاحاً أطول وأكثر عشوائية: {_gen_hint}'
        )


_validate_production_secret_key(SECRET_KEY)

from django.core.exceptions import ImproperlyConfigured as _ImproperlyConfigured

_agent_global_key = (env('ATTENDANCE_AGENT_API_KEY', default='') or '').strip()
if _agent_global_key and len(_agent_global_key) < 32:
    raise _ImproperlyConfigured(
        'ATTENDANCE_AGENT_API_KEY قصير جداً في الإنتاج (32 حرفاً كحد أدنى). '
        'يُفضّل مفاتيح لكل جهاز: python manage.py generate_attendance_agent_key --device-id=ID'
    )

ATTENDANCE_REQUIRE_INGEST_SIGNATURE = env.bool('ATTENDANCE_REQUIRE_INGEST_SIGNATURE', default=True)

if DEBUG:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured('DEBUG يجب أن يكون False في الإنتاج (DJANGO_ENV=production).')

# قراءة بروتوكول HTTPS من ترويسة X-Forwarded-Proto (يرسلها البروكسي)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# HTTPS — إن كانت CSRF_TRUSTED_ORIGINS كلها http:// (مثل IP:8082 بدون شهادة) يُفعَّل وضع HTTP تلقائياً
import os

_csrf_list = list(CSRF_TRUSTED_ORIGINS or [])
_http_csrf = [o for o in _csrf_list if o.startswith('http://')]
_https_csrf = [o for o in _csrf_list if o.startswith('https://')]
_other_csrf = [o for o in _csrf_list if o and not o.startswith(('http://', 'https://'))]

if _other_csrf:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        f'CSRF_TRUSTED_ORIGINS يجب أن تبدأ بـ http:// أو https://: {_other_csrf!r}'
    )
if _http_csrf and _https_csrf:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        'لا تخلط بين http:// و https:// في CSRF_TRUSTED_ORIGINS — اختر وضعاً واحداً.'
    )

_use_https_raw = os.environ.get('USE_HTTPS', '').strip().lower()
if _http_csrf and not _https_csrf:
    # نشر على IP/منفذ بدون TLS — يتغلّب على USE_HTTPS=true الخاطئ في .env
    if _use_https_raw in ('true', '1', 'yes'):
        import sys

        print(
            '[production] USE_HTTPS=true لكن CSRF_TRUSTED_ORIGINS=http فقط → تفعيل وضع HTTP '
            '(عطّل SSL redirect). يُفضّل USE_HTTPS=false في .env.',
            file=sys.stderr,
        )
    _USE_HTTPS = False
elif _use_https_raw in ('false', '0', 'no'):
    _USE_HTTPS = False
elif _use_https_raw in ('true', '1', 'yes'):
    _USE_HTTPS = True
else:
    _USE_HTTPS = True

SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=_USE_HTTPS)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=_USE_HTTPS)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=_USE_HTTPS)

# حماية الجلسات — كوكي الجلسة عبر HTTPS فقط، غير قابل للقراءة من JS، ينتهي عند إغلاق المتصفح
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = env.bool('SESSION_EXPIRE_AT_BROWSER_CLOSE', default=True)

# استثناء فحص الصحة من إعادة التوجيه إلى HTTPS (للمُراقبة الداخلية)
SECURE_REDIRECT_EXEMPT = [r'^health/$']

if _USE_HTTPS or SECURE_SSL_REDIRECT:
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
    SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=False)
    SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
    MIDDLEWARE = [m for m in MIDDLEWARE if m != 'config.middleware.DisableCOOPMiddleware']
else:
    # HTTP فقط — إبقاء DisableCOOPMiddleware لتجنب تحذيرات المتصفح على HTTP
    SECURE_CROSS_ORIGIN_OPENER_POLICY = None

from django.core.exceptions import ImproperlyConfigured

if not ALLOWED_HOSTS or ALLOWED_HOSTS == ['localhost', '127.0.0.1']:
    raise ImproperlyConfigured(
        'حدّد ALLOWED_HOSTS في .env بنطاق الإنتاج الفعلي (مثال: hr.example.com,72.61.107.230).'
    )
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        'حدّد CSRF_TRUSTED_ORIGINS في .env (مثال: http://72.61.107.230:8082 أو https://your-domain.com).'
    )
if _USE_HTTPS:
    for origin in CSRF_TRUSTED_ORIGINS:
        if not origin.startswith('https://'):
            raise ImproperlyConfigured(
                f'عند USE_HTTPS=true يجب أن تبدأ CSRF_TRUSTED_ORIGINS بـ https://: {origin!r} '
                f'أو اضبط USE_HTTPS=false للنشر على HTTP.'
            )
else:
    for origin in CSRF_TRUSTED_ORIGINS:
        if not origin.startswith('http://'):
            raise ImproperlyConfigured(
                f'في وضع HTTP يجب أن تبدأ CSRF_TRUSTED_ORIGINS بـ http://: {origin!r}'
            )

# حماية المتصفح
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# منع تحميل الموقع داخل iframe من مواقع خارجية
X_FRAME_OPTIONS = 'DENY'

# عند SESSION_EXPIRE_AT_BROWSER_CLOSE=true يُتجاهل SESSION_COOKIE_AGE (جلسة متصفح فقط)
SESSION_COOKIE_AGE = env.int('SESSION_COOKIE_AGE', default=28800)

# تقييد أقوى لمحاولات تسجيل الدخول عبر API
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_THROTTLE_RATES': {
        **REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'],
        'anon': env('DRF_ANON_THROTTLE', default='60/hour'),
        'user': env('DRF_USER_THROTTLE', default='500/hour'),
        'login': env('DRF_LOGIN_THROTTLE', default='10/hour'),
        'login_user': env('DRF_LOGIN_USER_THROTTLE', default='30/hour'),
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# CORS — مشاركة الموارد بين المواقع
# مطلوب إذا كانت الواجهة الأمامية على نطاق مختلف عن الـ API
# ══════════════════════════════════════════════════════════════════════════════
CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=False)
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True  # السماح بإرسال الكوكيز مع الطلبات

# ══════════════════════════════════════════════════════════════════════════════
# تسجيل الأحداث (Logging) — الإخراج إلى stdout (مناسب للحاويات/Docker)
# ══════════════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════════════
# تخزين الملفات — Cloudflare R2 (متوافق مع S3)
# تنظيم الملفات: HR/<نوع العملية>/<السنة>/<اسم الملف>
#
# عند تفعيل USE_R2=True:
#   - المستندات والمرفقات تُرفع مباشرة على R2
#   - الملفات الثابتة (CSS/JS) تُخدم عبر WhiteNoise
# عند USE_R2=False:
#   - الملفات تُخزّن محلياً على السيرفر (مناسب للتطوير فقط)
# ══════════════════════════════════════════════════════════════════════════════
USE_R2 = env.bool('USE_R2', default=False)

if USE_R2:
    # مفاتيح الوصول لـ Cloudflare R2
    AWS_ACCESS_KEY_ID = env('R2_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('R2_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env('R2_BUCKET_NAME', default='erphr')
    AWS_S3_ENDPOINT_URL = env('R2_ENDPOINT_URL')

    # المنطقة — R2 يستخدم 'auto' لكن boto3 يحتاج قيمة حقيقية للتوقيع
    AWS_S3_REGION_NAME = env('R2_REGION', default='auto')

    AWS_S3_FILE_OVERWRITE = False    # لا تكتب فوق ملف موجود — أنشئ اسماً جديداً
    AWS_DEFAULT_ACL = None            # بدون صلاحيات عامة افتراضية
    AWS_S3_SIGNATURE_VERSION = 's3v4' # إصدار التوقيع المطلوب
    AWS_S3_ADDRESSING_STYLE = 'path'  # أسلوب path أكثر موثوقية مع R2
    # روابط موقّعة — اضبط R2_SIGNED_URLS=false فقط إذا كان الـ bucket خاصاً بعناوين عامة موثوقة
    AWS_QUERYSTRING_AUTH = env.bool('R2_SIGNED_URLS', default=True)
    AWS_QUERYSTRING_EXPIRE = env.int('R2_SIGNED_URL_EXPIRE', default=3600)
    AWS_S3_VERIFY = True              # التحقق من شهادة SSL

    # نطاق مخصص للملفات (مثل: media.yourdomain.com)
    # إذا فارغ، يُستخدم رابط الـ bucket مباشرة
    AWS_S3_CUSTOM_DOMAIN = env('R2_PUBLIC_DOMAIN', default='')

    # تمرير المرفقات عبر Django (/media/...) للمستخدمين المسجّلين — bucket خاص
    R2_PROXY_MEDIA = env.bool('R2_PROXY_MEDIA', default=True)

    # محركات التخزين
    STORAGES = {
        'default': {
            'BACKEND': 'apps.core.storages.HRMediaStorage',   # تخزين الملفات المرفوعة
        },
        'staticfiles': {
            # مضغوط بدون manifest — يتوافق مع collectstatic عند بناء Docker (development)
            # Manifest كان يسبب 500 عند إضافة ملفات static جديدة (مثل css/login.css)
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }

    # رابط الوصول للملفات المرفوعة
    if R2_PROXY_MEDIA:
        MEDIA_URL = '/media/'
    elif AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    else:
        MEDIA_URL = f'{AWS_S3_ENDPOINT_URL.rstrip("/")}/{AWS_STORAGE_BUCKET_NAME}/'

# ══════════════════════════════════════════════════════════════════════════════
# Sentry — مراقبة أخطاء الإنتاج (اختياري)
# ══════════════════════════════════════════════════════════════════════════════

_SENTRY_DSN = env('SENTRY_DSN', default='').strip()
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=env.float('SENTRY_TRACES_SAMPLE_RATE', default=0.0),
        send_default_pii=False,
        environment=env('SENTRY_ENVIRONMENT', default='production'),
    )
