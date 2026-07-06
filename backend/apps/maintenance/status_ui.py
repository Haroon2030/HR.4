"""ألوان وأيقونات حالة طلب الصيانة — موحّدة مع تبويبات القائمة."""
from __future__ import annotations

from dataclasses import dataclass

from apps.maintenance.models import MaintenanceRequest


@dataclass(frozen=True)
class MaintenanceStatusUI:
    label: str
    icon: str
    badge_class: str


_STATUS_META: dict[str, tuple[str, str]] = {
    MaintenanceRequest.Status.PENDING: (
        'clock',
        'bg-amber-50 text-amber-800 border-amber-200',
    ),
    MaintenanceRequest.Status.ASSIGNED: (
        'user-cog',
        'bg-indigo-50 text-indigo-800 border-indigo-200',
    ),
    MaintenanceRequest.Status.WORKER_REPORTED: (
        'clipboard-check',
        'bg-purple-50 text-purple-800 border-purple-200',
    ),
    MaintenanceRequest.Status.MANAGER_CLOSED: (
        'building-2',
        'bg-sky-50 text-sky-800 border-sky-200',
    ),
    MaintenanceRequest.Status.BRANCH_CONFIRMED: (
        'check-circle-2',
        'bg-emerald-50 text-emerald-800 border-emerald-200',
    ),
    MaintenanceRequest.Status.RETURNED: (
        'rotate-ccw',
        'bg-rose-50 text-rose-800 border-rose-200',
    ),
}

_DEFAULT = ('help-circle', 'bg-slate-100 text-slate-700 border-slate-200')


def get_maintenance_status_ui(status: str | None) -> MaintenanceStatusUI:
    code = (status or '').strip()
    labels = dict(MaintenanceRequest.Status.choices)
    icon, badge = _STATUS_META.get(code, _DEFAULT)
    return MaintenanceStatusUI(
        label=labels.get(code, code or '—'),
        icon=icon,
        badge_class=f'border {badge}',
    )
