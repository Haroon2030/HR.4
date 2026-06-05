"""توجيه مرحلة الموافقة الأولى (مدير إدارة أو مدير فرع)."""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from apps.core.models import Notification


class FirstApproverKind:
    ADMINISTRATION = 'administration'
    BRANCH = 'branch'
    NONE = 'none'


TRANSFER_FIRST_APPROVER_LABEL = 'مدير إدارة العمليات'
OPERATIONS_ADMIN_SETTINGS_KEY = 'operations_administration_code'


@dataclass(frozen=True)
class FirstApproverDecision:
    kind: str
    recipient: object | None
    administration: object | None = None
    branch: object | None = None
    label_override: str | None = None

    @property
    def stage_label(self) -> str:
        if self.label_override:
            return self.label_override
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


def is_transfer_action(obj) -> bool:
    from apps.core.models import PendingAction

    return (
        isinstance(obj, PendingAction)
        and obj.action_type == PendingAction.ActionType.TRANSFER
    )


def get_operations_administration():
    """
    إدارة العمليات — جهة الموافقة الأولى لطلبات النقل (كل الفروع).
    يُحدَّد بالإعداد operations_administration_code أو باسم يحتوي «العمليات».
    """
    from apps.setup.models import Administration, SystemSettings

    qs = Administration.objects.filter(is_deleted=False, is_active=True).select_related('manager')
    code_row = SystemSettings.objects.filter(key=OPERATIONS_ADMIN_SETTINGS_KEY).values_list('value', flat=True).first()
    if code_row and str(code_row).strip():
        admin = qs.filter(code=str(code_row).strip()).first()
        if admin:
            return admin
    return qs.filter(name__icontains='العمليات').order_by('code').first()


def _transfer_first_approver_decision(obj) -> FirstApproverDecision | None:
    """موافقة أولى لطلب النقل → مدير إدارة العمليات دائماً."""
    ops_admin = get_operations_administration()
    manager = getattr(ops_admin, 'manager', None) if ops_admin else None
    if not ops_admin or not manager or not getattr(manager, 'is_active', False):
        return None
    return FirstApproverDecision(
        kind=FirstApproverKind.ADMINISTRATION,
        recipient=manager,
        administration=ops_admin,
        branch=getattr(obj, 'branch', None),
        label_override=TRANSFER_FIRST_APPROVER_LABEL,
    )


def resolve_first_approver(obj) -> FirstApproverDecision:
    """
    يحدد جهة الموافقة الأولى:
    - طلبات النقل: مدير إدارة العمليات (كل الفروع)
    - غير ذلك: مدير إدارة الموظف ثم مدير الفرع
    """
    if is_transfer_action(obj):
        transfer_decision = _transfer_first_approver_decision(obj)
        if transfer_decision:
            return transfer_decision

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
    if is_transfer_action(obj):
        ops_admin = get_operations_administration()
        if ops_admin and ops_admin.manager_id:
            return user.managed_administrations.filter(id=ops_admin.id).exists()
    decision = resolve_first_approver(obj)
    if decision.kind == FirstApproverKind.ADMINISTRATION:
        return user.managed_administrations.filter(id=decision.administration.id).exists()
    if decision.kind == FirstApproverKind.BRANCH:
        return user.managed_branches.filter(id=decision.branch.id).exists()
    return False


def first_stage_pending_q(
    user,
    *,
    model_status_pending_branch: str,
    supports_transfer: bool = False,
) -> Q:
    """
    فلتر صندوق الوارد للمرحلة الأولى:
    - مدير الإدارة يرى الطلبات ذات الإدارة التي يديرها.
    - مدير الفرع يرى الطلبات غير المرتبطة بإدارة مديرها فعّال.
    - طلبات النقل (PendingAction فقط): مدير إدارة العمليات يرى كل النقلات.
    """
    if user.is_superuser:
        return Q(status=model_status_pending_branch)

    admin_ids = list(
        user.managed_administrations.filter(is_deleted=False).values_list('id', flat=True)
    )
    branch_ids = list(
        user.managed_branches.filter(is_deleted=False).values_list('id', flat=True)
    )

    ops_admin_id = None
    transfer_type = None
    if supports_transfer:
        from apps.core.models import PendingAction

        transfer_type = PendingAction.ActionType.TRANSFER
        ops_admin = get_operations_administration()
        ops_admin_id = ops_admin.id if ops_admin else None

    q = Q()
    if admin_ids:
        q |= Q(status=model_status_pending_branch, administration_id__in=admin_ids)
        if supports_transfer and ops_admin_id and ops_admin_id in admin_ids:
            q |= Q(
                status=model_status_pending_branch,
                action_type=transfer_type,
            )
    if branch_ids:
        branch_q = Q(
            status=model_status_pending_branch,
            branch_id__in=branch_ids,
        ) & (
            Q(administration_id__isnull=True)
            | Q(administration__manager_id__isnull=True)
            | Q(administration__manager__is_active=False)
        )
        if supports_transfer:
            branch_q &= ~Q(action_type=transfer_type)
        q |= branch_q
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
