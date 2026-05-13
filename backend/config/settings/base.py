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

# وضع التصحيح — يُقرأ من .env
DEBUG = env('DEBUG')

# ⚠️ حماية: منع استخدام المفتاح الافتراضي في وضع الإنتاج
if not DEBUG and SECRET_KEY.startswith('django-insecure-dev-only'):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "SECRET_KEY غير مُعدّ في البيئة. حدّد SECRET_KEY في ملف .env قبل التشغيل في وضع الإنتاج."
    )

# النطاقات المسموح بها — تُقرأ من .env
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

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
    'corsheaders',                   # مشاركة الموارد بين المواقع
    'django_filters',               # فلاتر الاستعلامات
    'simple_history',                # سجل التدقيق التاريخي (Audit Log)
    
    # ── تطبيقات النظام المحلية ──
    'apps.core',                     # النواة (الصلاحيات، الإشعارات، دورة الموافقات)
    'apps.setup',                    # جداول الإعداد (جنسيات، مهن، بنوك، إلخ)
    'apps.cost_centers',             # مراكز التكلفة
    'apps.departments',              # الأقسام
    'apps.employees',                # الموظفين (ملفات، إجازات، عهد، سلف)
    'apps.payroll',                  # مسير الرواتب الشهري
]

# ══════════════════════════════════════════════════════════════════════════════
# الوسائط (Middleware) — ترتيب التنفيذ مهم!
# ══════════════════════════════════════════════════════════════════════════════

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',          # حماية أمنية أساسية
    'config.middleware.DisableCOOPMiddleware',                # إزالة COOP header (يسبب تحذيرات على HTTP)
    'whitenoise.middleware.WhiteNoiseMiddleware',             # خدمة الملفات الثابتة بكفاءة
    'django.middleware.gzip.GZipMiddleware',                  # ضغط الاستجابات (HTML/JSON)
    'corsheaders.middleware.CorsMiddleware',                  # معالجة CORS
    'django.contrib.sessions.middleware.SessionMiddleware',   # إدارة الجلسات
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
    # محركات الفلترة: فلاتر + بحث + ترتيب
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    # ترقيم الصفحات المخصص
    'DEFAULT_PAGINATION_CLASS': 'config.pagination.CustomPagination',
    'PAGE_SIZE': 8,
    # معالج أخطاء مخصص — يوحّد شكل الاستجابة
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_api_exception_handler',
}

# ══════════════════════════════════════════════════════════════════════════════
# إعدادات JWT — توكنات المصادقة
# ══════════════════════════════════════════════════════════════════════════════

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),    # صلاحية التوكن: ساعة
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),       # صلاحية تجديد التوكن: أسبوع
    'ROTATE_REFRESH_TOKENS': True,                     # إنشاء refresh جديد عند التجديد
    'BLACKLIST_AFTER_ROTATION': True,                  # حظر الـ refresh القديم
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
                'apps.core.context_processors.pending_actions_count',       # عدّاد الطلبات المعلّقة (sidebar)
                'apps.core.context_processors.approval_inbox',              # صندوق الوارد + الإشعارات
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

# ══════════════════════════════════════════════════════════════════════════════
# التحقق من كلمات المرور — 4 قواعد
# ══════════════════════════════════════════════════════════════════════════════

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},  # ليست مشابهة للاسم
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},             # 8 أحرف على الأقل
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},            # ليست شائعة
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},           # ليست أرقام فقط
]

# ══════════════════════════════════════════════════════════════════════════════
# التدويل — اللغة والمنطقة الزمنية
# ══════════════════════════════════════════════════════════════════════════════

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
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

# الملفات المرفوعة (media)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# حدود الرفع — حماية من الملفات الكبيرة
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024     # 15MB (فوق حد validators بـ 10MB)
FILE_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024     # 15MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000                # الحد من نماذج POST الكبيرة

# ══════════════════════════════════════════════════════════════════════════════
# المصادقة والجلسات
# ══════════════════════════════════════════════════════════════════════════════

LOGIN_URL = '/auth/login/'                          # صفحة تسجيل الدخول
LOGIN_REDIRECT_URL = '/'                            # بعد تسجيل الدخول → لوحة التحكم
LOGOUT_REDIRECT_URL = '/auth/login/'                # بعد تسجيل الخروج → صفحة الدخول

# إعدادات الجلسة
SESSION_COOKIE_AGE = 86400                          # مدة الجلسة: 24 ساعة
SESSION_SAVE_EVERY_REQUEST = True                   # تحديث الجلسة مع كل طلب
SESSION_EXPIRE_AT_BROWSER_CLOSE = False             # لا تنتهي عند إغلاق المتصفح

# ══════════════════════════════════════════════════════════════════════════════
# إعدادات أمنية متنوعة
# ══════════════════════════════════════════════════════════════════════════════

# تعطيل COOP header — يسبب تحذيرات على HTTP بدون HTTPS
SECURE_CROSS_ORIGIN_OPENER_POLICY = None

# نوع المفتاح التلقائي للنماذج
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
