"""تصفية طلبات الصيانة حسب نطاق الفرع والصلاحيات."""
from __future__ import annotations

from django.db.models import QuerySet

from apps.core.decorators import has_permission
from apps.core.models import Role
from apps.core.services.access_control import get_accessible_branch_ids


def user_sees_all_maintenance(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    role = getattr(profile, 'role', None) if profile else None
    if role and role.role_type == Role.RoleType.MAINTENANCE_MANAGER:
        return True
    return has_permission(user, 'maintenance.assign')


def filter_requests_for_user(user, qs: QuerySet):
    if user_sees_all_maintenance(user):
        return qs
    branch_ids = get_accessible_branch_ids(user)
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=branch_ids)
    return qs
