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
        if self.recipient:
            return approver_display_label(self.recipient)
        if self.kind == FirstApproverKind.ADMINISTRATION:
            return 'مدير الإدارة'
        if self.kind == FirstApproverKind.BRANCH:
            return 'مدير الفرع'
        return 'غير محدد'


def _profile_and_role(user):
    from apps.core.models import UserProfile

    profile = (
        UserProfile.objects.filter(user_id=user.pk)
        .select_related('role')
        .first()
    )
    return profile, (profile.role if profile else None)


def approver_display_label(user) -> str:
    """اسم الدور المعتمد للعرض (تبويب الموافقة الأولى وحالة الطلب)."""
    if not user:
        return 'غير محدد'
    _profile, role = _profile_and_role(user)
    if role and (role.name or '').strip():
        return role.name.strip()
    if role:
        label = role.get_role_type_display() or ''
        if '(' in label:
            label = label.split('(')[0].strip()
        return label or 'غير محدد'
    full = user.get_full_name() if hasattr(user, 'get_full_name') else ''
    return (full or getattr(user, 'username', '') or 'غير محدد').strip()


def first_stage_tab_label(user) -> str:
    """عنوان تبويب المرحلة الأولى حسب دور المستخدم الحالي."""
    from apps.core.models import Role

    _profile, role = _profile_and_role(user)

    if role and role.role_type in (
        Role.RoleType.ADMIN_MANAGER,
        Role.RoleType.MANAGER,
    ):
        return approver_display_label(user)

    if user.managed_administrations.filter(is_deleted=False).exists():
        return approver_display_label(user) if role else 'مدير الإدارة'

    if user.managed_branches.filter(is_deleted=False).exists():
        return approver_display_label(user) if role else 'مدير الفرع'

    if user.is_superuser:
        return 'موافقة أولى'

    return 'موافقة أولى'


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
