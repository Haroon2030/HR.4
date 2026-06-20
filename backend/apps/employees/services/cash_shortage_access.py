"""Branch accountant scoping for cashier shortage approvals."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.core.models import PendingAction, Role

User = get_user_model()


def is_branch_accountant(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    profile = getattr(user, 'profile', None)
    return bool(
        profile
        and profile.role
        and profile.role.role_type == Role.RoleType.BRANCH_ACCOUNTANT
    )


def branch_accountant_branch_ids(user) -> set[int]:
    """Branches a branch accountant may act on (profile.branch + assigned_branches)."""
    profile = getattr(user, 'profile', None)
    if not profile:
        return set()
    ids: set[int] = set()
    if profile.branch_id:
        ids.add(profile.branch_id)
    ids.update(
        profile.assigned_branches.filter(is_deleted=False).values_list('id', flat=True)
    )
    return ids


def branch_accountants_for_branch(branch_id):
    if not branch_id:
        return User.objects.none()
    return User.objects.filter(
        is_active=True,
        profile__role__role_type=Role.RoleType.BRANCH_ACCOUNTANT,
    ).filter(
        Q(profile__branch_id=branch_id)
        | Q(profile__assigned_branches=branch_id)
    ).distinct()


def user_can_approve_cash_shortage(user, action) -> bool:
    if user.is_superuser:
        return True
    if not is_branch_accountant(user):
        return False
    if action.action_type != PendingAction.ActionType.CASH_SHORTAGE:
        return False
    if action.status != PendingAction.Status.PENDING_BRANCH:
        return False
    branch_id = action.branch_id
    if not branch_id and action.employee_id:
        branch_id = getattr(action.employee, 'branch_id', None)
    if not branch_id:
        return False
    return branch_id in branch_accountant_branch_ids(user)


def cash_shortage_first_stage_q(user, *, model_status_pending_branch: str) -> Q:
    """Inbox filter: cash_shortage pending actions in accountant branch scope."""
    branch_ids = list(branch_accountant_branch_ids(user))
    if not branch_ids:
        return Q(pk__in=[])
    return Q(
        status=model_status_pending_branch,
        action_type=PendingAction.ActionType.CASH_SHORTAGE,
        branch_id__in=branch_ids,
    )
