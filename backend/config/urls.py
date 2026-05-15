"""
الروابط الرئيسية — Main URL Configuration
==========================================
هذا الملف يُوزّع كل الطلبات الواردة إلى الوجهة المناسبة:

  /admin/       → لوحة تحكم Django الإدارية
  /api/v1/      → واجهة REST API (الإصدار الأول)
  /api/token/   → مصادقة JWT (إنشاء/تجديد/تحقق)
  /api/docs/    → توثيق Swagger التفاعلي
  /             → واجهة الويب (Django Templates)
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

from config.health import health
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from config.jwt_views import (
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
    ThrottledTokenVerifyView,
)
from config.schema_permissions import StaffAuthenticated
from apps.core.media_views import serve_protected_media

urlpatterns = [
    path('health/', health, name='health'),
    # أيقونة المتصفح — تُعيد التوجيه لملف SVG ثابت
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.svg', permanent=True)),
    
    # لوحة الإدارة المدمجة في Django
    path('admin/', admin.site.urls),
    
    # واجهة REST API — الإصدار الأول
    path('api/v1/', include('config.api_urls')),
    
    # مصادقة JWT — إنشاء توكن جديد / تجديده / التحقق منه
    path('api/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', ThrottledTokenVerifyView.as_view(), name='token_verify'),
    
    # توثيق API — staff فقط في الإنتاج
    path(
        'api/schema/',
        SpectacularAPIView.as_view(permission_classes=[StaffAuthenticated]),
        name='schema',
    ),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(url_name='schema', permission_classes=[StaffAuthenticated]),
        name='swagger-ui',
    ),
    path(
        'api/redoc/',
        SpectacularRedocView.as_view(url_name='schema', permission_classes=[StaffAuthenticated]),
        name='redoc',
    ),
    
    # واجهة الويب (Django Templates) — تشمل كل صفحات النظام
    path('', include('config.web_urls')),
]

# في وضع التطوير: خدمة الملفات الثابتة والمرفقات محلياً
# في الإنتاج: يتولى WhiteNoise (ثابتة) وDjango (مرفقات)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# ملفات media المحلية — للمستخدمين المسجّلين فقط (R2 يُخدم عبر CDN منفصل)
if not getattr(settings, 'USE_R2', False):
    urlpatterns += [
        path('media/<path:path>', serve_protected_media, name='protected_media'),
    ]
