"""
صلاحيات دورة الموافقات (طلبات العمليات + التوظيف).
تُدمج مع فحص الأدوار/الفروع في _helpers._can_act_at_stage.
"""
from __future__ import annotations

from apps.core.decorators import has_permission, _is_super_or_admin
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
    'operations.approve_admin',
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
    """عرض قائمة/تفاصيل طلبات العمليات — صلاحيات DB فقط (بدون تجاوز بالدور الوظيفي)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or _is_super_or_admin(user):
        return True
    if has_permission(user, VIEW_PERMISSION):
        return True
    return any(
        has_permission(user, code)
        for code in WORKFLOW_PERMISSION_CODES
        if code != VIEW_PERMISSION
    )


def stage_permission_required(user, stage) -> bool:
    """فشل مغلق: بدون الصلاحية المناسبة → مرفوض (لا استثناء عند غياب السجل في DB)."""
    if user.is_superuser:
        return True
    if _is_super_or_admin(user):
        return True
    if stage == PendingAction.Stage.BRANCH:
        return (
            has_permission(user, 'operations.approve_branch')
            or has_permission(user, 'operations.approve_admin')
        )
    code = STAGE_PERMISSION.get(stage)
    if not code:
        return False
    return has_permission(user, code)


def can_return_operation(user) -> bool:
    if user.is_superuser:
        return True
    return has_permission(user, RETURN_PERMISSION)


def can_resubmit_operation(user) -> bool:
    if user.is_superuser:
        return True
    return has_permission(user, RESUBMIT_PERMISSION)


def user_can_reject_employment_request(user, emp_req) -> bool:
    """رفض/إرجاع طلب توظيف — operations.return + نطاق المرحلة (بدون تجاوز بالدور فقط)."""
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    if user.is_superuser or _is_super_or_admin(user):
        return True
    if not can_return_operation(user):
        return False

    from apps.employees.models import EmploymentRequest
    from apps.core.services.approval_routing import user_can_first_approve

    status = emp_req.status
    pending_branch = {
        EmploymentRequest.Status.PENDING_BRANCH,
        EmploymentRequest.Status.PENDING,
    }
    if status in pending_branch:
        return user_can_first_approve(user, emp_req)
    if status == EmploymentRequest.Status.PENDING_GM:
        return (
            has_permission(user, 'operations.approve_gm')
            or has_permission(user, 'operations.approve_admin')
        )
    if status == EmploymentRequest.Status.PENDING_OFFICER:
        return (
            emp_req.assigned_officer_id == user.id
            and has_permission(user, 'operations.approve_officer')
        )
    return False


def can_delete_pending_action(user, action) -> bool:
    """حذف/إخفاء طلب عملية — الإدارة لكل الحالات؛ المقدّم لطلباته بما فيها المكتملة."""
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    if user.is_superuser or _is_super_or_admin(user):
        return True
    if action.requested_by_id == user.id:
        return action.status in (
            PendingAction.Status.RETURNED,
            PendingAction.Status.PENDING_BRANCH,
            PendingAction.Status.APPROVED,
        )
    return False


def can_delete_employment_request(user, emp_req) -> bool:
    """حذف/إخفاء طلب توظيف — الإدارة لكل الحالات؛ المقدّم لطلباته بما فيها المكتملة."""
    from apps.employees.models import EmploymentRequest

    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    if user.is_superuser or _is_super_or_admin(user):
        return True
    if emp_req.requested_by_id == user.id:
        return emp_req.status in (
            EmploymentRequest.Status.PENDING_BRANCH,
            EmploymentRequest.Status.PENDING,
            EmploymentRequest.Status.REJECTED,
            EmploymentRequest.Status.APPROVED,
        )
    return False
