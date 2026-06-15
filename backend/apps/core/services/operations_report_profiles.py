"""ملفات تقارير العمليات حسب دور المستلم."""
from __future__ import annotations

from dataclasses import dataclass

from apps.setup.operations_report_recipients import OPERATIONS_REPORT_RECIPIENT_ROLES

# أدوار يستلمون التقرير الشامل (كل الأقسام — كل الموظفين)
FULL_REPORT_ROLE_KEYS: frozenset[str] = frozenset({
    'system_manager',
    'hr_manager',
    'executive_director',
})

# أقسام التقرير المالي/الإداري (حسب إدارة الموظف)
ADMIN_SCOPED_SECTION_KEYS: frozenset[str] = frozenset({
    'additions',
    'leaves',
    'absences',
    'terminations',
    'salary_adjustments',
})

OPERATIONS_SCOPED_SECTION_KEYS: frozenset[str] = frozenset({
    'additions',
    'transfers',
})

ALL_SECTION_KEYS: frozenset[str] = frozenset({
    'loans',
    'leaves',
    'transfers',
    'terminations',
    'absences',
    'additions',
    'salary_adjustments',
})


@dataclass(frozen=True)
class RoleReportProfile:
    role_key: str
    title: str
    section_keys: frozenset[str]
    scoped: bool


def get_role_report_profile(role_key: str | None) -> RoleReportProfile:
    """ملف التقرير لدور مستلم معيّن."""
    if not role_key or role_key in FULL_REPORT_ROLE_KEYS:
        label = dict(OPERATIONS_REPORT_RECIPIENT_ROLES).get(role_key or '', 'شامل')
        return RoleReportProfile(
            role_key=role_key or 'full',
            title=f'تقرير العمليات اليومي — {label}',
            section_keys=ALL_SECTION_KEYS,
            scoped=False,
        )

    if role_key == 'operations_manager':
        return RoleReportProfile(
            role_key=role_key,
            title='تقرير مدير العمليات — موظفون جدد وتنقلات',
            section_keys=OPERATIONS_SCOPED_SECTION_KEYS,
            scoped=True,
        )

    if role_key in ('finance_manager', 'data_manager', 'procurement_manager'):
        label = dict(OPERATIONS_REPORT_RECIPIENT_ROLES)[role_key]
        return RoleReportProfile(
            role_key=role_key,
            title=f'تقرير {label} — إدارة الموظفين',
            section_keys=ADMIN_SCOPED_SECTION_KEYS,
            scoped=True,
        )

    return RoleReportProfile(
        role_key=role_key,
        title='تقرير العمليات اليومي',
        section_keys=ALL_SECTION_KEYS,
        scoped=False,
    )
