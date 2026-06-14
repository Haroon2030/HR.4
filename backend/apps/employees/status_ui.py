"""تعريف موحّد لواجهة حالة الموظف — تسمية، أيقونة، لون، وإحصاءات لوحة التحكم."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.employees.models import Employee


@dataclass(frozen=True)
class EmployeeStatusUI:
    status: str
    label: str
    icon: str
    color: str
    stats_key: str
    badge_class: str
    badge_border_class: str


EMPLOYEE_STATUS_ORDER: tuple[str, ...] = (
    Employee.Status.ACTIVE,
    Employee.Status.LEAVE,
    Employee.Status.SUSPENDED,
    Employee.Status.TERMINATED,
)

_DEFAULT_UI = EmployeeStatusUI(
    status='',
    label='غير محدد',
    icon='user',
    color='suspended',
    stats_key='',
    badge_class='bg-slate-100 text-slate-700',
    badge_border_class='border border-slate-200',
)

_EMPLOYEE_STATUS_UI: dict[str, EmployeeStatusUI] = {
    Employee.Status.ACTIVE: EmployeeStatusUI(
        status=Employee.Status.ACTIVE,
        label=Employee.Status.ACTIVE.label,
        icon='user-check',
        color='active',
        stats_key='employees_active',
        badge_class='bg-emerald-100 text-emerald-700',
        badge_border_class='border border-emerald-200',
    ),
    Employee.Status.LEAVE: EmployeeStatusUI(
        status=Employee.Status.LEAVE,
        label=Employee.Status.LEAVE.label,
        icon='calendar-off',
        color='leave',
        stats_key='employees_leave',
        badge_class='bg-sky-100 text-sky-700',
        badge_border_class='border border-sky-200',
    ),
    Employee.Status.SUSPENDED: EmployeeStatusUI(
        status=Employee.Status.SUSPENDED,
        label=Employee.Status.SUSPENDED.label,
        icon='user-x',
        color='suspended',
        stats_key='employees_suspended',
        badge_class='bg-amber-100 text-amber-700',
        badge_border_class='border border-amber-200',
    ),
    Employee.Status.TERMINATED: EmployeeStatusUI(
        status=Employee.Status.TERMINATED,
        label=Employee.Status.TERMINATED.label,
        icon='user-minus',
        color='terminated',
        stats_key='employees_terminated',
        badge_class='bg-rose-100 text-rose-700',
        badge_border_class='border border-rose-200',
    ),
}


def get_employee_status_ui(status: str | None) -> EmployeeStatusUI:
    if not status:
        return _DEFAULT_UI
    return _EMPLOYEE_STATUS_UI.get(status, _DEFAULT_UI)


def build_employee_status_dashboard_rows(stats: dict[str, Any]) -> list[dict[str, Any]]:
    total = int(stats.get('employees_total') or 0)
    rows: list[dict[str, Any]] = []
    for status in EMPLOYEE_STATUS_ORDER:
        ui = get_employee_status_ui(status)
        count = int(stats.get(ui.stats_key) or 0)
        percent = round(count * 100 / total) if total else 0
        rows.append(
            {
                'status': ui.status,
                'label': ui.label,
                'icon': ui.icon,
                'color': ui.color,
                'count': count,
                'percent': percent,
            }
        )
    return rows


def employee_status_dist_palette() -> tuple[str, ...]:
    colors = tuple(get_employee_status_ui(status).color for status in EMPLOYEE_STATUS_ORDER)
    return colors + colors[:2]
