"""
روابط API — الإصدار الأول (v1)
================================
هذا الملف يحتوي على روابط واجهة REST API.
تُستخدم من قِبل التطبيقات الخارجية (موبايل، فرونت إند منفصل).

الروابط المتاحة:
  GET  /api/v1/companies/     — قائمة الشركات
  GET  /api/v1/branches/      — قائمة الفروع
  GET  /api/v1/roles/         — قائمة الأدوار
  GET  /api/v1/users/         — قائمة المستخدمين
  GET  /api/v1/me/            — بيانات المستخدم الحالي (الذي سجّل الدخول)

المصادقة:
  - JWT Token (Authorization: Bearer <token>)
  - أو Session Cookie (تسجيل دخول من واجهة الويب)
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.core.views import RoleViewSet, UserViewSet, current_user, BranchViewSet, CompanyViewSet

# إنشاء الـ Router — يولّد روابط CRUD تلقائياً لكل ViewSet
router = DefaultRouter()
router.register(r'companies', CompanyViewSet, basename='company')    # الشركات
router.register(r'branches', BranchViewSet, basename='branch')       # الفروع
router.register(r'roles', RoleViewSet, basename='role')              # الأدوار
router.register(r'users', UserViewSet, basename='user')              # المستخدمون

urlpatterns = [
    # روابط الـ ViewSets (CRUD تلقائي)
    path('', include(router.urls)),
    
    # بيانات المستخدم الحالي — GET /api/v1/me/
    path('me/', current_user, name='current-user'),
]
