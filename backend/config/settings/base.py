"""
الإعدادات الأساسية المشتركة — Base Settings
=============================================
هذا الملف يحتوي على الإعدادات المشتركة بين كل البيئات (تطوير + إنتاج).
يُستورد من settings/development.py و settings/production.py.

يشمل:
  1. المسارات الأساسية (BASE_DIR)
  2. إعدادات البيئة (SECRET_KEY, DEBUG)
  3. التطبيقات المُثبّتة (INSTALLED_APPS)
  4. الوسائط (Middleware)
  5. إعدادات REST Framework + JWT
  6. القوالب (Templates) + معالجات السياق
  7. قاعدة البيانات
  8. التحقق من كلمات المرور
  9. التدويل (اللغة والمنطقة الزمنية)
  10. الملفات الثابتة والمرفوعة
  11. إعدادات المصادقة والجلسات
"""

import environ
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# المسارات الأساسية
# ══════════════════════════════════════════════════════════════════════════════

# BASE_DIR = المجلد الرئيسي للمشروع (backend/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# CONFIG_DIR = مجلد الإعدادات (config/)
CONFIG_DIR = Path(__file__).resolve().parent.parent

# ══════════════════════════════════════════════════════════════════════════════
# إعدادات البيئة (متغيرات من ملف .env)
# ══════════════════════════════════════════════════════════════════════════════
env = environ.Env(
    DEBUG=(bool, False)  # القيمة الافتراضية: وضع الإنتاج (False)
)

# قراءة المتغيرات من ملف .env
environ.Env.read_env(BASE_DIR / '.env')

# المفتاح السري — يُقرأ من .env
# في التطوير: يُسمح بقيمة افتراضية. في الإنتاج: يُفرض من production.py
SECRET_KEY = env('SECRET_KEY', default='django-insecure-dev-only-NOT-FOR-PRODUCTION')

# وضع التصحيح — يُقرأ من .env (الافتراضي False؛ development.py يفرض True)
DEBUG = env.bool('DEBUG', default=False)

# ⚠️ حماية الإنتاج فقط — لا تُطبَّق أثناء تحميل development (CI بدون .env)
import os as _os
if _os.environ.get('DJANGO_ENV', '').lower() == 'production':
    if not DEBUG and str(SECRET_KEY).startswith('django-insecure-dev-only'):
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "SECRET_KEY غير مُعدّ في البيئة. حدّد SECRET_KEY في ملف .env قبل التشغيل في الإنتاج."
        )

# النطاقات المسموح بها — تُقرأ من .env
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

# مسار لوحة Django Admin (بدلاً من /admin الافتراضي)
DJANGO_ADMIN_URL = env('DJANGO_ADMIN_URL', default='secure-control-panel-2026').strip().strip('/')

# ══════════════════════════════════════════════════════════════════════════════
# التطبيقات المُثبّتة
# ══════════════════════════════════════════════════════════════════════════════

INSTALLED_APPS = [
    # ── تطبيقات Django المدمجة ──
    'django.contrib.admin',          # لوحة الإدارة
    'django.contrib.auth',           # نظام المصادقة
    'django.contrib.contenttypes',   # أنواع المحتوى
    'django.contrib.sessions',       # إدارة الجلسات
    'django.contrib.messages',       # رسائل المستخدم
    'django.contrib.staticfiles',    # الملفات الثابتة
    
    # ── تطبيقات الطرف الثالث ──
    'rest_framework',                # واجهة REST API
    'rest_framework_simplejwt',      # مصادقة JWT
    'rest_framework_simplejwt.token_blacklist',  # إبطال refresh tokens بعد التدوير
    'corsheaders',                   # مشاركة الموارد بين المواقع
    'django_filters',               # فلاتر الاستعلامات
    'simple_history',                # سجل التدقيق التاريخي (Audit Log)
    'drf_spectacular',               # توثيق OpenAPI (Swagger / ReDoc)
    
    # ── تطبيقات النظام المحلية ──
    'apps.core',                     # النواة (الصلاحيات، الإشعارات، دورة الموافقات)
    'apps.setup',                    # جداول الإعداد (جنسيات، مهن، بنوك، إلخ)
    'apps.cost_centers',             # مراكز التكلفة
    'apps.departments',              # الأقسام
    'apps.employees',                # الموظفين (ملفات، إجازات، عهد، سلف)
    'apps.payroll',                  # مسير الرواتب الشهري
    'apps.attendance.apps.AttendanceConfig',  # أجهزة البصمة والحضور
]

# ══════════════════════════════════════════════════════════════════════════════
# الوسائط (Middleware) — ترتيب التنفيذ مهم!
# ══════════════════════════════════════════════════════════════════════════════

MIDDLEWARE = [
    'config.middleware.ProxyForwardedHeadersMiddleware',  # قبل SecurityMiddleware — X-Forwarded-Proto
    'django.middleware.security.SecurityMiddleware',          # حماية أمنية أساسية
    'apps.attendance.middleware.AgentIngestBodyMiddleware',   # جسم خام لـ HMAC ingest
    'config.middleware.DisableCOOPMiddleware',                # إزالة COOP header (يسبب تحذيرات على HTTP)
    'whitenoise.middleware.WhiteNoiseMiddleware',             # خدمة الملفات الثابتة بكفاءة
    'django.middleware.gzip.GZipMiddleware',                  # ضغط الاستجابات (HTML/JSON)
    'corsheaders.middleware.CorsMiddleware',                  # معالجة CORS
    'django.contrib.sessions.middleware.SessionMiddleware',   # إدارة الجلسات
    'django.middleware.locale.LocaleMiddleware',            # لغة الواجهة (عربي)
    'django.middleware.common.CommonMiddleware',              # معالجة مشتركة
    'django.middleware.csrf.CsrfViewMiddleware',              # حماية CSRF
    'django.contrib.auth.middleware.AuthenticationMiddleware', # ربط المستخدم بالطلب
    'django.contrib.messages.middleware.MessageMiddleware',    # رسائل المستخدم
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # حماية من Clickjacking
    'simple_history.middleware.HistoryRequestMiddleware',      # التقاط المستخدم لسجل التدقيق
    'apps.core.middleware.AccessControlMiddleware',            # التحكم في الوصول للروابط
]

# ══════════════════════════════════════════════════════════════════════════════
# إعدادات REST Framework — واجهة API
# ══════════════════════════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    # طرق المصادقة: JWT (للتطبيقات) + Session (لواجهة الويب)
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    # الصلاحية الافتراضية: يجب تسجيل الدخول
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': env('DRF_ANON_THROTTLE', default='100/hour'),
        'user': env('DRF_USER_THROTTLE', default='1000/hour'),
        'login': env('DRF_LOGIN_THROTTLE', default='20/hour'),
        'login_user': env('DRF_LOGIN_USER_THROTTLE', default='60/hour'),
        'attendance_agent': env('DRF_ATTENDANCE_AGENT_THROTTLE', default='120/hour'),
    },
    # محركات الفلترة: فلاتر + بحث + ترتيب
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    # ترقيم الصفحات المخصص
    'DEFAULT_PAGINATION_CLASS': 'config.pagination.CustomPagination',
    'PAGE_SIZE': 8,
    # توثيق OpenAPI (drf-spectacular)
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # معالج أخطاء مخصص — يوحّد شكل الاستجابة
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_api_exception_handler',
}

# ══════════════════════════════════════════════════════════════════════════════
# إعدادات JWT — توكنات المصادقة
# ══════════════════════════════════════════════════════════════════════════════

from datetime import timedelta

_jwt_signing_key = (env('JWT_SECRET', default='') or '').strip()

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=env.int('JWT_ACCESS_TOKEN_MINUTES', default=15)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env.int('JWT_REFRESH_TOKEN_DAYS', default=7)),
    'ROTATE_REFRESH_TOKENS': True,                     # إنشاء refresh جديد عند التجديد
    'BLACKLIST_AFTER_ROTATION': True,                  # حظر الـ refresh القديم
}
if _jwt_signing_key:
    SIMPLE_JWT['SIGNING_KEY'] = _jwt_signing_key
    SIMPLE_JWT['VERIFYING_KEY'] = _jwt_signing_key

# ══════════════════════════════════════════════════════════════════════════════
# توثيق API — drf-spectacular
# ══════════════════════════════════════════════════════════════════════════════

SPECTACULAR_SETTINGS = {
    'TITLE': 'HR ERP API',
    'DESCRIPTION': 'REST API للنظام (شركات، فروع، أدوار، مستخدمون، JWT).',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
}

# ══════════════════════════════════════════════════════════════════════════════
# الروابط والقوالب
# ══════════════════════════════════════════════════════════════════════════════

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # مجلد القوالب الرئيسي
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',               # request في كل قالب
                'django.contrib.auth.context_processors.auth',              # user في كل قالب
                'django.contrib.messages.context_processors.messages',      # messages في كل قالب
                'apps.core.context_processors.sidebar_context',             # عدّادات sidebar (مخزّنة مؤقتاً)
                'apps.core.context_processors.app_info',                    # عن النظام (شركة / دعم / مطوّر)
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ══════════════════════════════════════════════════════════════════════════════
# قاعدة البيانات — SQLite افتراضياً (يُستبدل في production.py بـ PostgreSQL)
# ══════════════════════════════════════════════════════════════════════════════

DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3')
}

# تخزين مؤقت افتراضي (يُستبدل بـ Redis في production عند REDIS_URL)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'hr-default',
        'TIMEOUT': 300,
        'OPTIONS': {'MAX_ENTRIES': 5000},
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# التحقق من كلمات المرور
# ══════════════════════════════════════════════════════════════════════════════

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ══════════════════════════════════════════════════════════════════════════════
# التدويل — اللغة والمنطقة الزمنية
# ══════════════════════════════════════════════════════════════════════════════

LANGUAGE_CODE = 'ar'
LANGUAGES = [
    ('ar', 'العربية'),
]
TIME_ZONE = env('TIME_ZONE', default='Asia/Riyadh')
USE_I18N = True     # تفعيل الترجمة
USE_TZ = True       # تفعيل المنطقة الزمنية

# ══════════════════════════════════════════════════════════════════════════════
# الملفات الثابتة (CSS, JS, صور) + المرفوعة (مستندات، صور الموظفين)
# ══════════════════════════════════════════════════════════════════════════════

# الملفات الثابتة — تُخدم عبر WhiteNoise
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'            # مجلد التجميع (collectstatic)
STATICFILES_DIRS = [
    BASE_DIR / 'static',                           # مجلد المصدر
]

# محرك تخزين الملفات الثابتة — WhiteNoise مع ضغط
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# مدة تخزين الملفات الثابتة في المتصفح (ثانية) — مع أسماء ملفات مضغوطة من WhiteNoise
WHITENOISE_MAX_AGE = env.int('WHITENOISE_MAX_AGE', default=31536000)

# مدة تخزين عدادات الشريط الجانبي (ثانية) — يقلّل استعلامات COUNT على كل صفحة
SIDEBAR_COUNTS_CACHE_TTL = env.int('SIDEBAR_COUNTS_CACHE_TTL', default=45)
DASHBOARD_CACHE_TTL = env.int('DASHBOARD_CACHE_TTL', default=120)
SETUP_CACHE_TTL = env.int('SETUP_CACHE_TTL', default=3600)

# الملفات المرفوعة (media)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# حدود الرفع — متوافقة مع apps.core.validators (10MB)
_UPLOAD_LIMIT = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = _UPLOAD_LIMIT
FILE_UPLOAD_MAX_MEMORY_SIZE = _UPLOAD_LIMIT
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000                # الحد من نماذج POST الكبيرة

# ══════════════════════════════════════════════════════════════════════════════
# المصادقة والجلسات
# ══════════════════════════════════════════════════════════════════════════════

LOGIN_URL = '/auth/login/'                          # صفحة تسجيل الدخول
LOGIN_REDIRECT_URL = '/'                            # بعد تسجيل الدخول → لوحة التحكم
LOGOUT_REDIRECT_URL = '/auth/login/'                # بعد تسجيل الخروج → صفحة الدخول

# إعدادات الجلسة — حماية افتراضية (يُشدَّد في production.py)
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = env.bool('SESSION_EXPIRE_AT_BROWSER_CLOSE', default=True)
# يُستخدم فقط عند SESSION_EXPIRE_AT_BROWSER_CLOSE=False
SESSION_COOKIE_AGE = env.int('SESSION_COOKIE_AGE', default=28800)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SAMESITE = env('SESSION_COOKIE_SAMESITE', default='Lax')
CSRF_COOKIE_HTTPONLY = env.bool('CSRF_COOKIE_HTTPONLY', default=True)
CSRF_COOKIE_SAMESITE = env('CSRF_COOKIE_SAMESITE', default='Lax')

# ══════════════════════════════════════════════════════════════════════════════
# إعدادات البريد الإلكتروني (SMTP)
# تُقرأ من .env — إذا لم تكن مُعدّة، يُستخدم console backend (للتطوير)
# ══════════════════════════════════════════════════════════════════════════════

EMAIL_HOST = env('EMAIL_HOST', default='')
EMAIL_PORT = env.int('EMAIL_PORT', default=465)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=True)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER or 'noreply@localhost')
HR_NOTIFICATION_EMAIL = env('HR_NOTIFICATION_EMAIL', default='')
EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=30)

# اختيار الـ backend: إذا EMAIL_HOST مُعدّ نستخدم SMTP، وإلا نستخدم console (للتطوير المحلي)
if EMAIL_HOST:
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
else:
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')

# ══════════════════════════════════════════════════════════════════════════════
# WhatsApp — Evolution API
# ══════════════════════════════════════════════════════════════════════════════

WHATSAPP_ENABLED = env.bool('WHATSAPP_ENABLED', default=False)
EVOLUTION_API_URL = env('EVOLUTION_API_URL', default='').rstrip('/')
EVOLUTION_API_KEY = env('EVOLUTION_API_KEY', default='')
EVOLUTION_INSTANCE = env('EVOLUTION_INSTANCE', default='')
EVOLUTION_API_TIMEOUT = env.int('EVOLUTION_API_TIMEOUT', default=20)
WHATSAPP_DEFAULT_COUNTRY = env('WHATSAPP_DEFAULT_COUNTRY', default='966')
# إرسال إشعارات سير العمل في خلفية الطلب (لا يُفعَّل في التطوير/الاختبارات افتراضياً)
WHATSAPP_ASYNC_DISPATCH = env.bool('WHATSAPP_ASYNC_DISPATCH', default=False)

# ══════════════════════════════════════════════════════════════════════════════
# النسخ الاحتياطي لقاعدة البيانات (إشعارات + مسار الملفات)
# ══════════════════════════════════════════════════════════════════════════════

# مجلد النسخ المحلية (يتوافق مع أمر backup_db والحاوية Docker)
BACKUP_STORAGE_DIR = env('BACKUP_STORAGE_DIR', default='/app/backups')

# عناوين بريد تُرسل إليها نتيجة النسخ (مفصولة بفواصل). فارغ = لا إشعارات بريد
_backup_notify_raw = env('BACKUP_NOTIFY_EMAIL', default='')
BACKUP_NOTIFY_RECIPIENTS = [
    addr.strip() for addr in _backup_notify_raw.split(',') if addr.strip()
]
BACKUP_NOTIFY_ON_SUCCESS = env.bool('BACKUP_NOTIFY_ON_SUCCESS', default=True)
BACKUP_NOTIFY_ON_FAILURE = env.bool('BACKUP_NOTIFY_ON_FAILURE', default=True)

# نسخ تلقائي إلى R2 قبل تطبيق migrations (جداول / تغييرات على البيانات)
BACKUP_BEFORE_MIGRATE = env.bool('BACKUP_BEFORE_MIGRATE', default=True)
# إن true: فشل النسخ قبل migrate يوقف النشر (entrypoint) / يفشل أمر migrate
BACKUP_BEFORE_MIGRATE_REQUIRED = env.bool('BACKUP_BEFORE_MIGRATE_REQUIRED', default=False)

# ══════════════════════════════════════════════════════════════════════════════
# Rate limiting — django-ratelimit (يستخدم Django cache؛ Redis موصى به في الإنتاج)
# ══════════════════════════════════════════════════════════════════════════════
RATELIMIT_ENABLE = env.bool('RATELIMIT_ENABLE', default=True)
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_VIEW = 'config.ratelimit_handlers.ratelimited'

RATELIMIT_LOGIN_IP = env('RATELIMIT_LOGIN_IP', default='20/h')
RATELIMIT_LOGIN_USER = env('RATELIMIT_LOGIN_USER', default='20/h')
RATELIMIT_PASSWORD_CHANGE = env('RATELIMIT_PASSWORD_CHANGE', default='10/h')
RATELIMIT_API_TOKEN_IP = env('RATELIMIT_API_TOKEN_IP', default='30/h')
RATELIMIT_HEALTH_IP = env('RATELIMIT_HEALTH_IP', default='120/m')

# ══════════════════════════════════════════════════════════════════════════════
# إعدادات أمنية متنوعة
# ══════════════════════════════════════════════════════════════════════════════

# تعطيل COOP header — يسبب تحذيرات على HTTP بدون HTTPS
SECURE_CROSS_ORIGIN_OPENER_POLICY = None

# أجهزة البصمة (ZKTeco عبر IP — المنفذ الافتراضي 4370)
BIOMETRIC_MOCK_MODE = env.bool('BIOMETRIC_MOCK_MODE', default=False)
BIOMETRIC_ZK_TIMEOUT = env.int('BIOMETRIC_ZK_TIMEOUT', default=15)
BIOMETRIC_ZK_OMIT_PING = env.bool('BIOMETRIC_ZK_OMIT_PING', default=True)

# وكيل البصمة المحلي (وسيط بين جهاز ZK في الفرع والسيرفر السحابي)
ATTENDANCE_AGENT_API_KEY = env('ATTENDANCE_AGENT_API_KEY', default='')
# في الإنتاج: المفتاح العام لا يعرض قائمة الأجهزة/طلبات السحب (ingest يبقى مسموحاً)
AGENT_GLOBAL_KEY_LIST_DEVICES = env.bool('AGENT_GLOBAL_KEY_LIST_DEVICES', default=False)
AGENT_GLOBAL_KEY_ALLOW_INGEST = env.bool('AGENT_GLOBAL_KEY_ALLOW_INGEST', default=False)
# توقيع HMAC لطلبات ingest — افتراضياً معطّل في التطوير
ATTENDANCE_REQUIRE_INGEST_SIGNATURE = env.bool('ATTENDANCE_REQUIRE_INGEST_SIGNATURE', default=False)

# ── عن النظام (قائمة المعلومات في الشريط العلوي) ──
HR_APP_DEVELOPER = env('HR_APP_DEVELOPER', default='شركة الحلول التقنية')
HR_SUPPORT_PHONE = env('HR_SUPPORT_PHONE', default='+966531847156')
HR_APP_DESCRIPTION = env(
    'HR_APP_DESCRIPTION',
    default=(
        'نظام متكامل لإدارة الموارد البشرية: الموظفين، الرواتب، الحضور والانصراف، '
        'طلبات العمليات، التقارير والنماذج الرسمية — ضمن دورة موافقات واضحة.'
    ),
)

# نوع المفتاح التلقائي للنماذج
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
