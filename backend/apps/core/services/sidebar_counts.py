"""
عدادات الشريط الجانبي — مع تخزين مؤقت لتقليل استعلامات قاعدة البيانات على كل صفحة.
"""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = 'hr:sidebar_counts:'
DEFAULT_TTL = 90


def _cache_ttl() -> int:
    return int(getattr(settings, 'SIDEBAR_COUNTS_CACHE_TTL', DEFAULT_TTL))


def sidebar_counts_cache_key(user_id: int) -> str:
    return f'{CACHE_KEY_PREFIX}{user_id}'


def invalidate_sidebar_counts(*user_ids: int | None) -> None:
    """إبطال العدادات لمستخدمين محددين (بعد موافقة/إشعار)."""
    for uid in user_ids:
        if uid:
            cache.delete(sidebar_counts_cache_key(uid))


def _pending_statuses():
    from apps.core.models import PendingAction

    return [
        PendingAction.Status.PENDING_BRANCH,
        PendingAction.Status.PENDING_GM,
        PendingAction.Status.PENDING_OFFICER,
    ]


def _hire_pending_statuses():
    from apps.employees.models import EmploymentRequest

    return [
        EmploymentRequest.Status.PENDING_BRANCH,
        EmploymentRequest.Status.PENDING_GM,
        EmploymentRequest.Status.PENDING_OFFICER,
    ]


def _managed_branch_ids(user) -> list[int]:
    if user.is_superuser:
        return []
    return list(
        user.managed_branches.filter(is_deleted=False).values_list('id', flat=True)
    )


def _managed_administration_ids(user) -> list[int]:
    if user.is_superuser:
        return []
    return list(
        user.managed_administrations.filter(is_deleted=False).values_list('id', flat=True)
    )


def _compute_sidebar_counts(user) -> dict[str, int]:
    from apps.core.models import Notification, PendingAction
    from apps.core.services.approval_routing import first_stage_pending_q
    from apps.core.services.workflow_access import can_view_operations
    from apps.core.web_views._helpers import (
        _is_general_manager,
        _is_hr_officer,
    )
    from apps.employees.models import EmploymentRequest

    if not can_view_operations(user):
        return {
            'pending_actions_count': 0,
            'pending_for_me_count': 0,
            'unread_notifications_count': Notification.objects.filter(
                recipient=user, is_read=False,
            ).count(),
        }

    managed_ids = _managed_branch_ids(user)
    managed_admin_ids = _managed_administration_ids(user)
    pending_statuses = _pending_statuses()
    hire_statuses = _hire_pending_statuses()

    # ── إجمالي المعلّق (شارة القائمة) ──
    pa_qs = PendingAction.objects.filter(status__in=pending_statuses)
    hire_qs = EmploymentRequest.objects.filter(status__in=hire_statuses)

    if user.is_superuser:
        pa_total = pa_qs.count()
        hire_total = hire_qs.count()
    else:
        scope = Q(requested_by=user) | Q(assigned_officer=user)
        if managed_ids:
            scope |= Q(branch_id__in=managed_ids)
        if managed_admin_ids:
            scope |= Q(administration_id__in=managed_admin_ids)
        pa_total = pa_qs.filter(scope).distinct().count()
        hire_total = hire_qs.filter(scope).distinct().count()

    pending_actions_count = pa_total + hire_total

    # ── صندوق الوارد الشخصي + الإشعارات ──
    inbox_filter = Q()
    if user.is_superuser or _is_general_manager(user):
        inbox_filter |= Q(status=PendingAction.Status.PENDING_GM)
    first_pa_q = first_stage_pending_q(
        user,
        model_status_pending_branch=PendingAction.Status.PENDING_BRANCH,
    )
    if first_pa_q.children:
        inbox_filter |= first_pa_q
    elif user.is_superuser:
        inbox_filter |= Q(status=PendingAction.Status.PENDING_BRANCH)
    if _is_hr_officer(user):
        inbox_filter |= Q(
            status=PendingAction.Status.PENDING_OFFICER,
            assigned_officer=user,
        )
    elif user.is_superuser:
        inbox_filter |= Q(status=PendingAction.Status.PENDING_OFFICER)
    inbox_filter |= Q(status=PendingAction.Status.RETURNED, requested_by=user)

    pa_for_me = (
        PendingAction.objects.filter(inbox_filter).distinct().count()
        if inbox_filter
        else 0
    )

    hire_inbox = Q()
    if user.is_superuser or _is_general_manager(user):
        hire_inbox |= Q(status=EmploymentRequest.Status.PENDING_GM)
    first_hire_q = first_stage_pending_q(
        user,
        model_status_pending_branch=EmploymentRequest.Status.PENDING_BRANCH,
    )
    if first_hire_q.children:
        hire_inbox |= first_hire_q
    elif user.is_superuser:
        hire_inbox |= Q(status=EmploymentRequest.Status.PENDING_BRANCH)
    if _is_hr_officer(user):
        hire_inbox |= Q(
            status=EmploymentRequest.Status.PENDING_OFFICER,
            assigned_officer=user,
        )
    elif user.is_superuser:
        hire_inbox |= Q(status=EmploymentRequest.Status.PENDING_OFFICER)

    hire_for_me = (
        EmploymentRequest.objects.filter(hire_inbox).distinct().count()
        if hire_inbox
        else 0
    )

    unread = Notification.objects.filter(recipient=user, is_read=False).count()

    return {
        'pending_actions_count': pending_actions_count,
        'pending_for_me_count': pa_for_me + hire_for_me,
        'unread_notifications_count': unread,
    }


def get_sidebar_counts(user) -> dict[str, int]:
    """جلب العدادات من الذاكرة المؤقتة أو حسابها مرة واحدة."""
    key = sidebar_counts_cache_key(user.pk)
    cached: dict[str, Any] | None = cache.get(key)
    if cached is not None:
        return cached

    try:
        data = _compute_sidebar_counts(user)
        cache.set(key, data, _cache_ttl())
        return data
    except Exception as exc:
        logger.warning('get_sidebar_counts failed: %s', exc)
        return {
            'pending_actions_count': 0,
            'pending_for_me_count': 0,
            'unread_notifications_count': 0,
        }
