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
SECRET_KEY = env('SECRET_KEY')

# وضع التصحيح — يجب أن يكون False في الإنتاج دائماً
DEBUG = env.bool('DEBUG', default=False)

# النطاقات/العناوين المسموح لها بالوصول للسيرفر
ALLOWED_HOSTS = env.list(
    'ALLOWED_HOSTS',
    default=['72.61.107.230', 'localhost', '127.0.0.1'],
)

# النطاقات الموثوقة لحماية CSRF (مطلوبة لنماذج POST)
CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS',
    default=[
        'http://72.61.107.230',
        'http://72.61.107.230:8082',
    ],
)

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

# إعدادات التوافق مع Neon / PgBouncer:
# - تعطيل المؤشرات من جانب السيرفر (غير مدعومة في وضع transaction pooling)
# - تشفير SSL إجباري لقواعد البيانات السحابية
# - إبقاء الاتصال حياً عبر TCP keepalives لمنع قطعه بواسطة الشبكة
DATABASES['default'].setdefault('DISABLE_SERVER_SIDE_CURSORS', True)
_db_options = DATABASES['default'].setdefault('OPTIONS', {})
_db_options.setdefault('sslmode', env('DB_SSLMODE', default='require'))
_db_options.setdefault('connect_timeout', 10)        # مهلة الاتصال: 10 ثوانٍ
_db_options.setdefault('keepalives', 1)               # تفعيل keepalive
_db_options.setdefault('keepalives_idle', 30)          # إرسال أول keepalive بعد 30 ثانية من السكون
_db_options.setdefault('keepalives_interval', 10)      # تكرار keepalive كل 10 ثوانٍ
_db_options.setdefault('keepalives_count', 5)           # إغلاق الاتصال بعد 5 محاولات فاشلة

# ══════════════════════════════════════════════════════════════════════════════
# التخزين المؤقت (Cache)
# يستخدم ذاكرة العملية (LocMemCache) — مناسب لسيرفر واحد (VPS).
# إذا توسّع النظام لأكثر من worker، استخدم Redis بدلاً منه.
# ══════════════════════════════════════════════════════════════════════════════
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'hr-default',
        'TIMEOUT': 300,                      # انتهاء الصلاحية: 5 دقائق
        'OPTIONS': {'MAX_ENTRIES': 5000},     # الحد الأقصى للعناصر المُخزّنة
    }
}

# استخدام التخزين المؤقت للجلسات أيضاً — يقلل الضغط على قاعدة البيانات
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

# ══════════════════════════════════════════════════════════════════════════════
# الأمان — السيرفر خلف Reverse Proxy (Traefik عبر Dokploy)
# ══════════════════════════════════════════════════════════════════════════════

# قراءة بروتوكول HTTPS من ترويسة X-Forwarded-Proto (يرسلها Traefik)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# إعادة التوجيه لـ HTTPS — معطّل لأن Traefik يتولى ذلك
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)

# حماية ملفات الكوكيز — تُفعّل عند استخدام HTTPS
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=False)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=False)

# حماية المتصفح من هجمات XSS وContent-Type sniffing
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# منع تحميل الموقع داخل iframe من مواقع خارجية (حماية من Clickjacking)
X_FRAME_OPTIONS = 'SAMEORIGIN'

# ══════════════════════════════════════════════════════════════════════════════
# CORS — مشاركة الموارد بين المواقع
# مطلوب إذا كانت الواجهة الأمامية على نطاق مختلف عن الـ API
# ══════════════════════════════════════════════════════════════════════════════
CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=False)
CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS',
    default=[
        'http://72.61.107.230',
        'http://72.61.107.230:8082',
    ],
)
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

# #region agent log - Temporary debug for R2 settings verification
import json
import time
log_data = {
    'USE_R2': USE_R2,
    'R2_ACCESS_KEY_SET': bool(env('R2_ACCESS_KEY_ID', default='')),
    'R2_SECRET_KEY_SET': bool(env('R2_SECRET_ACCESS_KEY', default='')), 
    'R2_BUCKET_NAME': env('R2_BUCKET_NAME', default=''),
    'R2_ENDPOINT_URL': env('R2_ENDPOINT_URL', default=''),
}
try:
    with open('debug-7f44e5.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps({'sessionId': '7f44e5', 'location': 'production.py:164', 'message': 'Production settings loaded', 'data': log_data, 'timestamp': time.time() * 1000, 'hypothesisId': 'SETTINGS'}) + '\n')
except Exception:
    pass
# #endregion

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
    AWS_QUERYSTRING_AUTH = False       # روابط الملفات بدون توقيع (عامة)
    AWS_S3_VERIFY = True              # التحقق من شهادة SSL

    # نطاق مخصص للملفات (مثل: media.yourdomain.com)
    # إذا فارغ، يُستخدم رابط الـ bucket مباشرة
    AWS_S3_CUSTOM_DOMAIN = env('R2_PUBLIC_DOMAIN', default='')

    # محركات التخزين
    STORAGES = {
        'default': {
            'BACKEND': 'apps.core.storages.HRMediaStorage',   # تخزين الملفات المرفوعة
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',  # الملفات الثابتة
        },
    }

    # رابط الوصول للملفات المرفوعة
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    else:
        MEDIA_URL = f'{AWS_S3_ENDPOINT_URL.rstrip("/")}/{AWS_STORAGE_BUCKET_NAME}/'
