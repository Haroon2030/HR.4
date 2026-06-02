"""
صلاحيات دورة الموافقات (طلبات العمليات + التوظيف).
تُدمج مع فحص الأدوار/الفروع في _helpers._can_act_at_stage.
"""
from __future__ import annotations

from apps.core.decorators import has_permission
from apps.core.models import PendingAction

STAGE_PERMISSION = {
    PendingAction.Stage.BRANCH: 'operations.approve_branch',
    PendingAction.Stage.GM: 'operations.approve_gm',
    PendingAction.Stage.OFFICER: 'operations.approve_officer',
}

RETURN_PERMISSION = 'operations.return'
RESUBMIT_PERMISSION = 'operations.resubmit'
VIEW_PERMISSION = 'operations.view'

WORKFLOW_PERMISSION_CODES = (
    VIEW_PERMISSION,
    'operations.approve_branch',
    'operations.approve_administration',
    'operations.approve_gm',
    'operations.approve_officer',
    RETURN_PERMISSION,
    RESUBMIT_PERMISSION,
)

from apps.core.permissions_registry import register_module, register_permission

register_module('operations', name='طلبات العمليات', icon='list-checks', order=12)
for _code in WORKFLOW_PERMISSION_CODES:
    register_permission(_code)


def can_view_operations(user) -> bool:
    """عرض قائمة/تفاصيل طلبات العمليات."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if has_permission(user, VIEW_PERMISSION):
        return True
    if has_permission(user, 'employees.edit'):
        return True
    from apps.core.web_views._helpers import (
        _is_branch_manager,
        _is_general_manager,
        _is_hr_officer,
    )
    return (
        _is_branch_manager(user)
        or _is_general_manager(user)
        or _is_hr_officer(user)
    )


def stage_permission_required(user, stage) -> bool:
    if user.is_superuser:
        return True
    code = STAGE_PERMISSION.get(stage)
    if not code:
        return False
    if stage == PendingAction.Stage.BRANCH:
        if has_permission(user, 'operations.approve_branch') or has_permission(user, 'operations.approve_administration'):
            return True
        from apps.core.models import Permission
        if not Permission.objects.filter(
            code__in=['operations.approve_branch', 'operations.approve_administration'],
            is_active=True,
        ).exists():
            return True
        return False

    if has_permission(user, code):
        return True
    from apps.core.models import Permission

    if not Permission.objects.filter(code=code, is_active=True).exists():
        return True
    return False


def can_return_operation(user) -> bool:
    if user.is_superuser:
        return True
    if has_permission(user, RETURN_PERMISSION):
        return True
    from apps.core.models import Permission
    if not Permission.objects.filter(code=RETURN_PERMISSION, is_active=True).exists():
        return True
    return False


def can_resubmit_operation(user) -> bool:
    if user.is_superuser:
        return True
    if has_permission(user, RESUBMIT_PERMISSION):
        return True
    from apps.core.models import Permission
    if not Permission.objects.filter(code=RESUBMIT_PERMISSION, is_active=True).exists():
        return True
    return False
