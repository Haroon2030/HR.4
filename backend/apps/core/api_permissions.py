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


class DenyUnmappedAPIAction(BasePermission):
    """يرفض أي action في ViewSet غير مُعرَّف في permission_map."""

    def has_permission(self, request, view):
        action = getattr(view, 'action', None)
        if not action:
            return True
        permission_map = getattr(view, 'permission_map', None) or {}
        return action in permission_map


class ActionPermissionMixin:
    """
    ViewSet mixin: set permission_map = {'list': 'users.view', 'create': 'users.add', ...}.
    أي action غير مذكور في permission_map يُرفض (لا يكفي تسجيل الدخول فقط).
    """

    permission_map: dict = {}

    def get_permissions(self):
        action = getattr(self, 'action', None)
        handler = getattr(self, action, None) if action else None
        if handler is not None:
            action_permission_classes = getattr(handler, 'permission_classes', None)
            if action_permission_classes is not None:
                return [cls() for cls in action_permission_classes]

        code = self.permission_map.get(action)
        if code:
            return [IsAuthenticated(), has_app_permission(code)()]
        return [IsAuthenticated(), DenyUnmappedAPIAction()]
