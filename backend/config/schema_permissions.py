"""
Restrict OpenAPI schema / Swagger / ReDoc to staff users in production.
"""
from rest_framework.permissions import BasePermission, IsAuthenticated


class IsStaffOrReadOnlyInDebug(BasePermission):
    """Staff-only API documentation when DEBUG is False."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from django.conf import settings

        if settings.DEBUG:
            return True
        return bool(request.user.is_staff or request.user.is_superuser)


class StaffAuthenticated(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        from django.conf import settings

        if settings.DEBUG:
            return True
        return bool(request.user.is_staff or request.user.is_superuser)
