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
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

urlpatterns = [
    # أيقونة المتصفح — تُعيد التوجيه لملف SVG ثابت
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.svg', permanent=True)),
    
    # لوحة الإدارة المدمجة في Django
    path('admin/', admin.site.urls),
    
    # واجهة REST API — الإصدار الأول
    path('api/v1/', include('config.api_urls')),
    
    # مصادقة JWT — إنشاء توكن جديد / تجديده / التحقق منه
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # توثيق API تفاعلي (Swagger / ReDoc)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # واجهة الويب (Django Templates) — تشمل كل صفحات النظام
    path('', include('config.web_urls')),
]

# في وضع التطوير: خدمة الملفات الثابتة والمرفقات محلياً
# في الإنتاج: يتولى WhiteNoise (ثابتة) وDjango (مرفقات)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# خدمة ملفات الميديا (المرفقات) دائماً — ضرورية لعرض المستندات المرفوعة
urlpatterns += [
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
]
