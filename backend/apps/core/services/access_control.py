"""
Centralized RBAC helpers — user administration, branch scoping, role hierarchy.
"""
from __future__ import annotations

from typing import Iterable

from django.contrib.auth import get_user_model
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from apps.core.models import Branch, Role

User = get_user_model()

_MISSING = object()

ROLE_RANK = {
    Role.RoleType.EMPLOYEE: 10,
    Role.RoleType.SPECIALIST: 20,
    Role.RoleType.HR_OFFICER: 30,
    Role.RoleType.MANAGER: 40,
    Role.RoleType.BRANCH_ACCOUNTANT: 42,
    Role.RoleType.ADMIN_MANAGER: 45,
    Role.RoleType.HR_MANAGER: 90,
    Role.RoleType.ADMIN: 100,
}

PRIVILEGED_ROLE_TYPES = frozenset({
    Role.RoleType.ADMIN,
    Role.RoleType.HR_MANAGER,
})

# صلاحيات توسّع نطاق الفروع لكل الموظفين (مالية / رواتب / تقارير شاملة)
COMPANY_WIDE_BRANCH_PERMISSIONS = frozenset({
    'payroll.process',
    'payroll.manage',
    'reports.view_all',
})

SENSITIVE_USER_PERMISSIONS = frozenset({
    'users.edit',
    'users.delete',
    'users.add',
})


def role_rank(role: Role | None) -> int:
    if not role:
        return 0
    return ROLE_RANK.get(role.role_type, 0)


def actor_role(user) -> Role | None:
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


def is_super_or_admin(user) -> bool:
    if user.is_superuser:
        return True
    role = actor_role(user)
    return bool(role and role.role_type == Role.RoleType.ADMIN)


def is_privileged_actor(user) -> bool:
    """Superuser or admin / HR manager role types."""
    if user.is_superuser:
        return True
    role = actor_role(user)
    return bool(role and role.role_type in PRIVILEGED_ROLE_TYPES)


def has_company_wide_branch_access(user) -> bool:
    """أدوار المالية/الرواتب أو التقارير الشاملة — كل الفروع."""
    if is_privileged_actor(user):
        return True
    from apps.core.decorators import get_user_permissions

    return bool(COMPANY_WIDE_BRANCH_PERMISSIONS.intersection(get_user_permissions(user)))


def get_accessible_branch_ids(user) -> set[int] | None:
    """
    None → unrestricted branch access (superuser, admin, HR manager).
    Otherwise a set of branch primary keys.
    """
    cached = getattr(user, '_accessible_branch_ids_cache', _MISSING)
    if cached is not _MISSING:
        return cached

    if user.is_superuser:
        result = None
        user._accessible_branch_ids_cache = result
        return result

    if has_company_wide_branch_access(user):
        user._accessible_branch_ids_cache = None
        return None

    profile = getattr(user, 'profile', None)
    if profile and profile.role and profile.role.role_type in (
        Role.RoleType.ADMIN,
        Role.RoleType.HR_MANAGER,
    ):
        user._accessible_branch_ids_cache = None
        return None

    ids: set[int] = set(
        user.managed_branches.filter(is_deleted=False).values_list('id', flat=True)
    )
    admin_ids = list(
        user.managed_administrations.filter(is_deleted=False).values_list('id', flat=True)
    )
    if admin_ids:
        from apps.employees.models import Employee

        ids.update(
            Employee.objects.filter(
                administration_id__in=admin_ids,
                is_deleted=False,
            ).values_list('branch_id', flat=True)
        )
    if profile:
        if profile.branch_id:
            ids.add(profile.branch_id)
        ids.update(
            profile.assigned_branches.filter(is_deleted=False).values_list('id', flat=True)
        )
    user._accessible_branch_ids_cache = ids
    return ids


def get_all_active_branches_queryset() -> QuerySet:
    return Branch.objects.filter(is_deleted=False, is_active=True).order_by('name')


def get_all_active_branches_list() -> list[Branch]:
    """قائمة الفروع النشطة — مُخزّنة مؤقتاً لتجنب تكرار الاستعلام في نفس الطلب."""
    from django.core.cache import cache

    key = 'hr:branches:active_list_v1'
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = list(get_all_active_branches_queryset())
    cache.set(key, data, 300)
    return data


def filter_branches_queryset(user, queryset: QuerySet) -> QuerySet:
    branch_ids = get_accessible_branch_ids(user)
    if branch_ids is None:
        return queryset
    return queryset.filter(pk__in=branch_ids)


def user_in_accessible_branches(user, target_user) -> bool:
    branch_ids = get_accessible_branch_ids(user)
    if branch_ids is None:
        return True

    profile = getattr(target_user, 'profile', None)
    if not profile:
        return False

    if profile.branch_id and profile.branch_id in branch_ids:
        return True

    if profile.assigned_branches.filter(pk__in=branch_ids).exists():
        return True

    return False


def filter_users_queryset(actor, queryset: QuerySet) -> QuerySet:
    branch_ids = get_accessible_branch_ids(actor)
    if branch_ids is None:
        return queryset

    return queryset.filter(
        Q(profile__branch_id__in=branch_ids)
        | Q(profile__assigned_branches__in=branch_ids)
    ).distinct()


def order_users_queryset(queryset: QuerySet) -> QuerySet:
    """ترتيب المستخدمين: الأعلى رتبةً أولاً، ثم رقم المستخدم، ثم اسم الدخول."""
    whens = [
        When(profile__role__role_type=role_type, then=Value(rank))
        for role_type, rank in ROLE_RANK.items()
    ]
    return queryset.annotate(
        _sort_rank=Case(*whens, default=Value(0), output_field=IntegerField()),
    ).order_by('-_sort_rank', 'profile__user_number', 'username')


def order_roles_queryset(queryset: QuerySet) -> QuerySet:
    """ترتيب الأدوار حسب التسلسل التقني في role_catalog."""
    from apps.core.role_catalog import ROLE_TYPE_ORDER

    whens = [
        When(role_type=role_type, then=Value(idx))
        for idx, role_type in enumerate(ROLE_TYPE_ORDER)
    ]
    return queryset.annotate(
        _sort_type=Case(*whens, default=Value(99), output_field=IntegerField()),
    ).order_by('_sort_type', 'name')


def assignable_roles_queryset(actor, queryset: QuerySet | None = None) -> QuerySet:
    qs = queryset if queryset is not None else Role.objects.filter(is_active=True)
    if actor.is_superuser:
        return qs

    actor_r = actor_role(actor)
    max_rank = role_rank(actor_r)

    if is_super_or_admin(actor):
        return qs.exclude(role_type=Role.RoleType.ADMIN)

    return qs.filter(
        role_type__in=[
            rt for rt, rank in ROLE_RANK.items() if rank <= max_rank
        ]
    ).exclude(role_type__in=PRIVILEGED_ROLE_TYPES)


def can_assign_role(actor, new_role: Role | None) -> bool:
    if actor.is_superuser:
        return True
    if new_role is None:
        return True
    if new_role.role_type in PRIVILEGED_ROLE_TYPES:
        return is_privileged_actor(actor)
    return role_rank(new_role) <= role_rank(actor_role(actor))


def target_is_protected(user) -> bool:
    profile = getattr(user, 'profile', None)
    return bool(profile and getattr(profile, 'is_protected', False))


def can_view_user(actor, target_user) -> bool:
    if actor.is_superuser or actor.pk == target_user.pk:
        return True
    if not user_in_accessible_branches(actor, target_user):
        return False
    if target_is_protected(target_user) and not actor.is_superuser:
        actor_r = actor_role(actor)
        target_r = actor_role(target_user)
        if role_rank(target_r) >= role_rank(actor_r) and not is_super_or_admin(actor):
            return False
    return True


def can_administer_user(actor, target_user) -> bool:
    """May edit/delete/manage permissions for target (excluding self-elevation)."""
    if actor.is_superuser:
        return True

    if target_is_protected(target_user):
        return False

    if actor.pk == target_user.pk:
        return False

    if not user_in_accessible_branches(actor, target_user):
        return False

    actor_r = actor_role(actor)
    target_r = actor_role(target_user)

    if is_super_or_admin(actor):
        return role_rank(target_r) < role_rank(actor_r) or (
            actor_r and actor_r.role_type == Role.RoleType.ADMIN
        )

    return role_rank(actor_r) > role_rank(target_r)


def can_manage_user_permissions(actor, target_user) -> bool:
    if not can_administer_user(actor, target_user):
        return False
    return is_privileged_actor(actor)


def validate_user_admin_changes(
    actor,
    target_user,
    *,
    new_role: Role | None = None,
    password: str | None = None,
    is_active: bool | None = None,
    branch: Branch | None = None,
    assigned_branch_ids: Iterable[int] | None = None,
) -> str | None:
    """
    Validate sensitive user-administration changes.
    Returns an Arabic error message, or None if allowed.
    """
    if target_is_protected(target_user) and not actor.is_superuser:
        return 'المستخدم محمي — التعديل متاح لمدير النظام (superuser) فقط.'

    if actor.pk == target_user.pk and not actor.is_superuser:
        if new_role is not None and new_role != actor_role(actor):
            return 'لا يمكنك تغيير دورك بنفسك.'
        if is_active is False:
            return 'لا يمكنك تعطيل حسابك بنفسك.'

    if not can_administer_user(actor, target_user) and actor.pk != target_user.pk:
        return 'لا تملك صلاحية إدارة هذا المستخدم.'

    if new_role is not None and not can_assign_role(actor, new_role):
        return 'لا يمكنك تعيين هذا الدور.'

    if password and target_is_protected(target_user) and not actor.is_superuser:
        return 'لا يمكن تغيير كلمة مرور مستخدم محمي إلا من مدير النظام.'

    if is_active is False and target_is_protected(target_user):
        return 'لا يمكن تعطيل مستخدم محمي.'

    accessible = get_accessible_branch_ids(actor)
    if accessible is not None:
        if branch is not None and branch.pk not in accessible:
            return 'لا يمكنك تعيين فرع خارج نطاق صلاحياتك.'
        if assigned_branch_ids is not None:
            invalid = set(assigned_branch_ids) - accessible
            if invalid:
                return 'لا يمكنك تعيين فروع خارج نطاق صلاحياتك.'

    return None


def validate_permission_grants(actor, permission_codes: Iterable[str]) -> str | None:
    """Block non-privileged actors from granting sensitive user-admin permissions."""
    if is_privileged_actor(actor):
        return None
    blocked = SENSITIVE_USER_PERMISSIONS.intersection(set(permission_codes))
    if blocked:
        return 'لا يمكنك منح صلاحيات إدارة المستخدمين.'
    return None
