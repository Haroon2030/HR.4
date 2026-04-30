"""
API URLs - v1
نظام إدارة الموارد البشرية
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.core.views import RoleViewSet, UserViewSet, current_user, BranchViewSet, CompanyViewSet

# Create router
router = DefaultRouter()
router.register(r'companies', CompanyViewSet, basename='company')
router.register(r'branches', BranchViewSet, basename='branch')
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    # ViewSets
    path('', include(router.urls)),
    
    # Current User
    path('me/', current_user, name='current-user'),
]
