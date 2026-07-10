"""بيانات لوحة تحكم الصيانة — KPIs، اتجاه أسبوعي، وتوزيعات."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from apps.maintenance.models import MaintenanceRequest
from apps.maintenance.status_ui import get_maintenance_status_ui

_STATUS_ORDER: tuple[str, ...] = (
    MaintenanceRequest.Status.PENDING,
    MaintenanceRequest.Status.ASSIGNED,
    MaintenanceRequest.Status.WORKER_REPORTED,
    MaintenanceRequest.Status.MANAGER_CLOSED,
    MaintenanceRequest.Status.BRANCH_CONFIRMED,
    MaintenanceRequest.Status.RETURNED,
)

_STATUS_KPI_THEME: dict[str, str] = {
    MaintenanceRequest.Status.PENDING: 'amber',
    MaintenanceRequest.Status.ASSIGNED: 'indigo',
    MaintenanceRequest.Status.WORKER_REPORTED: 'purple',
    MaintenanceRequest.Status.MANAGER_CLOSED: 'cyan',
    MaintenanceRequest.Status.BRANCH_CONFIRMED: 'emerald',
    MaintenanceRequest.Status.RETURNED: 'rose',
}

_STATUS_DONUT_FILL: dict[str, str] = {
    MaintenanceRequest.Status.PENDING: '#f59e0b',
    MaintenanceRequest.Status.ASSIGNED: '#6366f1',
    MaintenanceRequest.Status.WORKER_REPORTED: '#a855f7',
    MaintenanceRequest.Status.MANAGER_CLOSED: '#0ea5e9',
    MaintenanceRequest.Status.BRANCH_CONFIRMED: '#10b981',
    MaintenanceRequest.Status.RETURNED: '#f43f5e',
}

_STATUS_LEGEND_COLOR: dict[str, str] = {
    MaintenanceRequest.Status.PENDING: 'amber',
    MaintenanceRequest.Status.ASSIGNED: 'indigo',
    MaintenanceRequest.Status.WORKER_REPORTED: 'purple',
    MaintenanceRequest.Status.MANAGER_CLOSED: 'leave',
    MaintenanceRequest.Status.BRANCH_CONFIRMED: 'active',
    MaintenanceRequest.Status.RETURNED: 'terminated',
}


def _base_queryset():
    return MaintenanceRequest.objects.filter(is_deleted=False)


def build_maintenance_status_donut_style(rows: list[dict[str, Any]]) -> str:
    """CSS conic-gradient for maintenance status donut chart."""
    total = sum(int(row.get('count') or 0) for row in rows)
    if total <= 0:
        return 'conic-gradient(#e2e8f0 0deg 360deg)'

    parts: list[str] = []
    angle = 0.0
    for row in rows:
        count = int(row.get('count') or 0)
        if count <= 0:
            continue
        sweep = count * 360.0 / total
        status = str(row.get('status') or '')
        fill = _STATUS_DONUT_FILL.get(status, '#94a3b8')
        end = angle + sweep
        parts.append(f'{fill} {angle:.2f}deg {end:.2f}deg')
        angle = end

    if not parts:
        return 'conic-gradient(#e2e8f0 0deg 360deg)'
    return f"conic-gradient({', '.join(parts)})"


def build_maintenance_dashboard() -> dict[str, Any]:
    """إحصائيات الصيانة لمدير النظام/المدير العام — كل الفروع."""
    qs = _base_queryset()
    open_qs = qs.exclude(status=MaintenanceRequest.Status.BRANCH_CONFIRMED)

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    kpis = {
        'open_total': open_qs.count(),
        'pending': qs.filter(status=MaintenanceRequest.Status.PENDING).count(),
        'assigned': qs.filter(status=MaintenanceRequest.Status.ASSIGNED).count(),
        'awaiting_close': qs.filter(status=MaintenanceRequest.Status.WORKER_REPORTED).count(),
        'awaiting_confirm': qs.filter(status=MaintenanceRequest.Status.MANAGER_CLOSED).count(),
        'completed_month': qs.filter(
            status=MaintenanceRequest.Status.BRANCH_CONFIRMED,
            branch_confirmed_at__gte=month_start,
        ).count(),
        'urgent_open': open_qs.filter(priority=MaintenanceRequest.Priority.URGENT).count(),
    }

    status_count_map: dict[str, int] = {
        row['status']: row['c']
        for row in qs.values('status').annotate(c=Count('id'))
    }
    total_requests = sum(status_count_map.values())

    status_rows: list[dict[str, Any]] = []
    for status in _STATUS_ORDER:
        ui = get_maintenance_status_ui(status)
        count = status_count_map.get(status, 0)
        percent = round(count * 100 / total_requests) if total_requests else 0
        status_rows.append(
            {
                'status': status,
                'label': ui.label,
                'count': count,
                'percent': percent,
                'theme': _STATUS_KPI_THEME.get(status, 'slate'),
                'icon': ui.icon,
                'color': _STATUS_LEGEND_COLOR.get(status, 'suspended'),
            }
        )

    today = timezone.localdate()
    weekly_trend: list[dict[str, Any]] = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        weekly_trend.append(
            {
                'date': day.isoformat(),
                'label': day.strftime('%d/%m'),
                'count': qs.filter(requested_at__date=day).count(),
            }
        )
    max_weekly = max((row['count'] for row in weekly_trend), default=1) or 1

    top_branches = list(
        open_qs.values('branch__name')
        .annotate(c=Count('id'))
        .order_by('-c')[:5]
    )
    max_branch_open = max((row['c'] for row in top_branches), default=1) or 1

    list_url = reverse('web:list_maintenance_requests')
    kpi_links = {
        'open_total': f'{list_url}?tab=all',
        'pending': f'{list_url}?tab=pending',
        'assigned': f'{list_url}?tab=assigned',
        'awaiting_close': f'{list_url}?tab=worker_reported',
        'awaiting_confirm': f'{list_url}?tab=manager_closed',
        'completed_month': f'{list_url}?tab=branch_confirmed',
        'urgent_open': f'{list_url}?tab=all',
    }

    return {
        'kpis': kpis,
        'kpi_links': kpi_links,
        'status_rows': status_rows,
        'total_requests': total_requests,
        'weekly_trend': weekly_trend,
        'max_weekly': max_weekly,
        'top_branches': top_branches,
        'max_branch_open': max_branch_open,
    }
