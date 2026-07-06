"""مستخدمو إشعارات الصيانة."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.core.models import Role

User = get_user_model()


def maintenance_manager_users():
    return User.objects.filter(
        is_active=True,
    ).filter(
        Q(profile__role__role_type=Role.RoleType.MAINTENANCE_MANAGER)
        | Q(profile__role__permissions__code='maintenance.assign'),
    ).distinct()


def branch_manager_for_request(req):
    branch = req.branch
    if branch and branch.manager_id:
        return branch.manager
    return None
