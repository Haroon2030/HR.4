"""تخزين مؤقت لإحصائيات لوحة التحكم (KPI + توزيعات) — لكل مستخدم ونطاق فروعه."""
from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q

CACHE_PREFIX = 'hr:dashboard_overview:'
OVERVIEW_VER_PREFIX = 'hr:dashboard_overview_ver:'
DEFAULT_TTL = 120


def _cache_ttl() -> int:
    return int(getattr(settings, 'DASHBOARD_CACHE_TTL', DEFAULT_TTL))


def _branch_scope_digest(accessible_branch_ids: list[int] | None) -> str:
    if accessible_branch_ids is None:
        return 'all'
    raw = ','.join(str(i) for i in sorted(accessible_branch_ids))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


def _overview_version(user_id: int) -> int:
    return int(cache.get(f'{OVERVIEW_VER_PREFIX}{user_id}') or 0)


def dashboard_overview_cache_key(user_id: int, accessible_branch_ids: list[int] | None) -> str:
    return (
        f'{CACHE_PREFIX}{user_id}:{_overview_version(user_id)}:'
        f'{_branch_scope_digest(accessible_branch_ids)}'
    )


def invalidate_dashboard_overview(*user_ids: int | None) -> None:
    """يزيد رقم النسخة فيُبطِل كل مفاتيح overview لهذا المستخدم."""
    for uid in user_ids:
        if not uid:
            continue
        vkey = f'{OVERVIEW_VER_PREFIX}{uid}'
        try:
            cache.incr(vkey)
        except ValueError:
            cache.set(vkey, 1, timeout=None)


def cache_bypass_requested(request) -> bool:
    return (request.GET.get('refresh') or '').strip() == '1'


def _compute_dashboard_overview(user, accessible_branch_ids: list[int] | None) -> dict[str, Any]:
    from apps.core.models import Branch, PendingAction
    from apps.employees.models import Employee, EmploymentRequest

    emp_qs_all = Employee.objects.filter(is_deleted=False)
    if not user.is_superuser and accessible_branch_ids:
        emp_qs_all = emp_qs_all.filter(branch_id__in=accessible_branch_ids)

    emp_status_counts = emp_qs_all.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status=Employee.Status.ACTIVE)),
        leave=Count('id', filter=Q(status=Employee.Status.LEAVE)),
        suspended=Count('id', filter=Q(status=Employee.Status.SUSPENDED)),
        terminated=Count('id', filter=Q(status=Employee.Status.TERMINATED)),
    )

    er_qs = EmploymentRequest.objects.filter(is_deleted=False)
    if not user.is_superuser and accessible_branch_ids:
        er_qs = er_qs.filter(branch_id__in=accessible_branch_ids)
    er_open_count = er_qs.exclude(
        status__in=[
            EmploymentRequest.Status.APPROVED,
            EmploymentRequest.Status.REJECTED,
        ],
    ).count()

    pa_qs = (
        PendingAction.objects.filter(is_deleted=False)
        if hasattr(PendingAction, 'is_deleted')
        else PendingAction.objects.all()
    )
    if not user.is_superuser and accessible_branch_ids:
        pa_qs = pa_qs.filter(branch_id__in=accessible_branch_ids)
    _clearance_types = [
        PendingAction.ActionType.CUSTODY_CLEAR,
        PendingAction.ActionType.TERMINATE,
        PendingAction.ActionType.CONTRACT_END,
        PendingAction.ActionType.END_OF_SERVICE,
    ]
    pa_stats = pa_qs.aggregate(
        open_count=Count('id', filter=~Q(status=PendingAction.Status.APPROVED)),
        clearance_count=Count(
            'id',
            filter=Q(action_type__in=_clearance_types)
            & ~Q(status=PendingAction.Status.APPROVED),
        ),
    )

    branch_distribution = list(
        emp_qs_all.values('branch__name')
        .annotate(c=Count('id'))
        .order_by('-c')[:6]
    )
    max_branch = max((b['c'] for b in branch_distribution), default=1) or 1

    gender_distribution = list(
        emp_qs_all.values('gender').annotate(c=Count('id')).order_by('-c')
    )
    max_gender = max((g['c'] for g in gender_distribution), default=1) or 1

    nationality_distribution = list(
        emp_qs_all.values('nationality__name')
        .annotate(c=Count('id'))
        .order_by('-c')[:6]
    )
    max_nationality = max((n['c'] for n in nationality_distribution), default=1) or 1

    stats = {
        'employees_total': emp_status_counts['total'] or 0,
        'employees_active': emp_status_counts['active'] or 0,
        'employees_leave': emp_status_counts['leave'] or 0,
        'employees_suspended': emp_status_counts['suspended'] or 0,
        'employees_terminated': emp_status_counts['terminated'] or 0,
        'employment_requests_open': er_open_count,
        'pending_actions_open': pa_stats['open_count'] or 0,
        'clearance_open': pa_stats['clearance_count'] or 0,
        'branches_count': (
            Branch.objects.filter(is_deleted=False).count()
            if user.is_superuser
            else len(accessible_branch_ids or [])
        ),
    }

    from apps.employees.status_ui import build_employee_status_dashboard_rows

    return {
        'stats': stats,
        'employee_status_rows': build_employee_status_dashboard_rows(stats),
        'branch_distribution': branch_distribution,
        'max_branch': max_branch,
        'gender_distribution': gender_distribution,
        'max_gender': max_gender,
        'nationality_distribution': nationality_distribution,
        'max_nationality': max_nationality,
    }


def get_dashboard_overview(
    user,
    accessible_branch_ids: list[int] | None,
    *,
    bypass: bool = False,
) -> tuple[dict[str, Any], bool]:
    """يُرجع (overview_dict, from_cache)."""
    key = dashboard_overview_cache_key(user.pk, accessible_branch_ids)
    if not bypass:
        cached = cache.get(key)
        if cached is not None:
            return cached, True

    data = _compute_dashboard_overview(user, accessible_branch_ids)
    cache.set(key, data, _cache_ttl())
    return data, False
