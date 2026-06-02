"""توجيه مرحلة الموافقة الأولى (مدير إدارة أو مدير فرع)."""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from apps.core.models import Notification


class FirstApproverKind:
    ADMINISTRATION = 'administration'
    BRANCH = 'branch'
    NONE = 'none'


@dataclass(frozen=True)
class FirstApproverDecision:
    kind: str
    recipient: object | None
    administration: object | None = None
    branch: object | None = None

    @property
    def stage_label(self) -> str:
        if self.kind == FirstApproverKind.ADMINISTRATION:
            return 'مدير الإدارة'
        if self.kind == FirstApproverKind.BRANCH:
            return 'مدير الفرع'
        return 'غير محدد'


def snapshot_routing_fields(employee) -> dict:
    """لقطة مسار الموافقة عند إنشاء الطلب."""
    return {
        'branch': getattr(employee, 'branch', None),
        'administration': getattr(employee, 'administration', None),
    }


def resolve_first_approver(obj) -> FirstApproverDecision:
    """
    يحدد جهة الموافقة الأولى:
    1) مدير الإدارة (إذا وُجد مدير نشط)
    2) وإلا مدير الفرع
    """
    administration = getattr(obj, 'administration', None)
    admin_manager = getattr(administration, 'manager', None) if administration else None
    if admin_manager and getattr(admin_manager, 'is_active', False):
        return FirstApproverDecision(
            kind=FirstApproverKind.ADMINISTRATION,
            recipient=admin_manager,
            administration=administration,
            branch=getattr(obj, 'branch', None),
        )

    branch = getattr(obj, 'branch', None)
    branch_manager = getattr(branch, 'manager', None) if branch else None
    if branch_manager and getattr(branch_manager, 'is_active', False):
        return FirstApproverDecision(
            kind=FirstApproverKind.BRANCH,
            recipient=branch_manager,
            administration=administration,
            branch=branch,
        )

    return FirstApproverDecision(
        kind=FirstApproverKind.NONE,
        recipient=None,
        administration=administration,
        branch=branch,
    )


def user_can_first_approve(user, obj) -> bool:
    if user.is_superuser:
        return True
    decision = resolve_first_approver(obj)
    if decision.kind == FirstApproverKind.ADMINISTRATION:
        return user.managed_administrations.filter(id=decision.administration.id).exists()
    if decision.kind == FirstApproverKind.BRANCH:
        return user.managed_branches.filter(id=decision.branch.id).exists()
    return False


def first_stage_pending_q(user, *, model_status_pending_branch: str) -> Q:
    """
    فلتر صندوق الوارد للمرحلة الأولى:
    - مدير الإدارة يرى الطلبات ذات الإدارة التي يديرها.
    - مدير الفرع يرى الطلبات غير المرتبطة بإدارة مديرها فعّال.
    """
    if user.is_superuser:
        return Q(status=model_status_pending_branch)

    admin_ids = list(
        user.managed_administrations.filter(is_deleted=False).values_list('id', flat=True)
    )
    branch_ids = list(
        user.managed_branches.filter(is_deleted=False).values_list('id', flat=True)
    )

    q = Q()
    if admin_ids:
        q |= Q(status=model_status_pending_branch, administration_id__in=admin_ids)
    if branch_ids:
        q |= Q(
            status=model_status_pending_branch,
            branch_id__in=branch_ids,
        ) & (
            Q(administration_id__isnull=True)
            | Q(administration__manager_id__isnull=True)
            | Q(administration__manager__is_active=False)
        )
    return q


def notify_on_first_stage(
    obj,
    *,
    title: str,
    message: str = '',
    icon: str = 'inbox',
    color: str = Notification.Color.PRIMARY,
):
    """إشعار مدير الإدارة/الفرع حسب قرار التوجيه."""
    from apps.core.services import notifications as notif
    from apps.employees.models import EmploymentRequest

    decision = resolve_first_approver(obj)
    if not decision.recipient:
        return None

    if isinstance(obj, EmploymentRequest):
        return notif.notify(
            decision.recipient,
            title=title,
            message=message,
            link='/employment-requests/',
            icon=icon,
            color=color,
        )
    return notif.notify(
        decision.recipient,
        title=title,
        message=message,
        link=notif.notify_action_url(obj),
        icon=icon,
        color=color,
        related_action=obj,
    )
