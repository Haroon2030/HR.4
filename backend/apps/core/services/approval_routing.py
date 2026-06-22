"""توجيه مرحلة الموافقة الأولى (مدير إدارة أو مدير فرع)."""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from apps.core.models import Notification


class FirstApproverKind:
    ADMINISTRATION = 'administration'
    BRANCH = 'branch'
    BRANCH_ACCOUNTANT = 'branch_accountant'
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
        if self.kind == FirstApproverKind.BRANCH_ACCOUNTANT:
            return 'محاسب الفرع'
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
    """اسم الدور المعتمد للعرض (تبويب الموافقة الأولى وحالة الطلب) — عربي فقط."""
    from apps.core.role_catalog import arabic_role_label

    if not user:
        return 'غير محدد'
    _profile, role = _profile_and_role(user)
    if role:
        label = arabic_role_label(role_type=role.role_type, name=getattr(role, 'name', None))
        if label and label != '—':
            return label
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

    from apps.employees.services.cash_shortage_access import is_branch_accountant
    if is_branch_accountant(user):
        return approver_display_label(user) if role else 'محاسب الفرع'

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
    - عجز كاشير → محاسب الفرع
    - وإلا: مدير الإدارة (إذا وُجد) ثم مدير الفرع
    """
    from apps.core.models import PendingAction

    if isinstance(obj, PendingAction) and obj.action_type == PendingAction.ActionType.CASH_SHORTAGE:
        branch = getattr(obj, 'branch', None) or getattr(getattr(obj, 'employee', None), 'branch', None)
        return FirstApproverDecision(
            kind=FirstApproverKind.BRANCH_ACCOUNTANT,
            recipient=None,
            branch=branch,
            administration=getattr(obj, 'administration', None),
        )

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
    from apps.core.models import PendingAction
    from apps.employees.services.cash_shortage_access import user_can_approve_cash_shortage

    if user.is_superuser:
        return True
    if isinstance(obj, PendingAction) and obj.action_type == PendingAction.ActionType.CASH_SHORTAGE:
        return user_can_approve_cash_shortage(user, obj)
    decision = resolve_first_approver(obj)
    if decision.kind == FirstApproverKind.ADMINISTRATION:
        return user.managed_administrations.filter(id=decision.administration.id).exists()
    if decision.kind == FirstApproverKind.BRANCH:
        return user.managed_branches.filter(id=decision.branch.id).exists()
    return False


def first_stage_pending_q(user, *, model_status_pending_branch: str) -> Q:
    """
    فلتر صندوق الوارد للمرحلة الأولى:
    - محاسب الفرع: عجز الكاشير فقط في فروعه
    - مدير الإدارة: طلبات إدارته (ما عدا عجز الكاشير)
    - مدير الفرع: طلبات فرعه غير المرتبطة بإدارة فعّالة (ما عدا عجز الكاشier)
    """
    from apps.core.models import PendingAction
    from apps.employees.services.cash_shortage_access import (
        cash_shortage_first_stage_q,
        is_branch_accountant,
    )

    if user.is_superuser:
        return Q(status=model_status_pending_branch)

    q = Q()
    if is_branch_accountant(user):
        cs_q = cash_shortage_first_stage_q(user, model_status_pending_branch=model_status_pending_branch)
        if cs_q.children:
            q |= cs_q

    admin_ids = list(
        user.managed_administrations.filter(is_deleted=False).values_list('id', flat=True)
    )
    branch_ids = list(
        user.managed_branches.filter(is_deleted=False).values_list('id', flat=True)
    )
    non_cash = ~Q(action_type=PendingAction.ActionType.CASH_SHORTAGE)
    if admin_ids:
        q |= Q(status=model_status_pending_branch, administration_id__in=admin_ids) & non_cash
    if branch_ids:
        q |= Q(
            status=model_status_pending_branch,
            branch_id__in=branch_ids,
        ) & non_cash & (
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
    """إشعار مدير الإدارة/الفرع أو محاسب الفرع حسب قرار التوجيه."""
    from apps.core.models import PendingAction
    from apps.core.services import notifications as notif
    from apps.employees.models import EmploymentRequest
    from apps.employees.services.cash_shortage_access import branch_accountants_for_branch

    if isinstance(obj, PendingAction) and obj.action_type == PendingAction.ActionType.CASH_SHORTAGE:
        branch_id = obj.branch_id or (obj.employee.branch_id if obj.employee_id else None)
        recipients = branch_accountants_for_branch(branch_id)
        first = None
        for recipient in recipients:
            first = notif.notify_user(
                recipient,
                obj,
                title=title,
                message=message,
                icon=icon,
                color=color,
            )
        from apps.core.services.whatsapp import workflow_notifier
        workflow_notifier.notify_whatsapp_first_stage(obj, title=title, message=message)
        return first

    decision = resolve_first_approver(obj)
    if not decision.recipient:
        return None

    from apps.core.services.whatsapp import workflow_notifier

    if isinstance(obj, EmploymentRequest):
        result = notif.notify(
            decision.recipient,
            title=title,
            message=message,
            link='/employment-requests/',
            icon=icon,
            color=color,
        )
    else:
        result = notif.notify(
            decision.recipient,
            title=title,
            message=message,
            link=notif.notify_action_url(obj),
            icon=icon,
            color=color,
            related_action=obj,
        )
    workflow_notifier.notify_whatsapp_first_stage(obj, title=title, message=message)
    return result
