"""
DRF permission classes aligned with apps.core.decorators RBAC.
"""
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.core.decorators import has_permission


def has_app_permission(permission_code: str):
    """Return a DRF permission class for a single RBAC code."""

    class _HasAppPermission(BasePermission):
        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False
            if request.user.is_superuser:
                return True
            return has_permission(request.user, permission_code)

    _HasAppPermission.__name__ = f'HasAppPermission_{permission_code.replace(".", "_")}'
    _HasAppPermission.__qualname__ = _HasAppPermission.__name__
    return _HasAppPermission


class ActionPermissionMixin:
    """
    ViewSet mixin: set permission_map = {'list': 'users.view', 'create': 'users.add', ...}.
    Unlisted actions require IsAuthenticated only (avoid for sensitive endpoints).
    """

    permission_map: dict = {}

    def get_permissions(self):
        code = self.permission_map.get(getattr(self, 'action', None))
        if code:
            return [IsAuthenticated(), has_app_permission(code)()]
        return [IsAuthenticated()]
