"""
شاشات فرعية للحضور والبصمة — وحدة مستقلة لكل شاشة في مصفوفة الصلاحيات.

صلاحية attendance.view تمنح تلقائياً كل شاشات العرض الفرعية (توافق مع الأدوار الحالية).
الشاشات الفردية لا تُوسَّع إلى attendance.view حتى لا يُفتح الوصول لكل الشاشات.
"""
from __future__ import annotations

from apps.core.permissions_registry import register_module, register_permission

ATTENDANCE_SCREEN_DEVICES_VIEW = 'attendance_screen_devices.view'
ATTENDANCE_SCREEN_REPORT_VIEW = 'attendance_screen_report.view'
ATTENDANCE_SCREEN_LATE_ALERTS_VIEW = 'attendance_screen_late_alerts.view'
ATTENDANCE_SCREEN_RECORDS_VIEW = 'attendance_screen_records.view'

ATTENDANCE_SCREEN_VIEW_CODES: frozenset[str] = frozenset({
    ATTENDANCE_SCREEN_DEVICES_VIEW,
    ATTENDANCE_SCREEN_REPORT_VIEW,
    ATTENDANCE_SCREEN_LATE_ALERTS_VIEW,
    ATTENDANCE_SCREEN_RECORDS_VIEW,
})

_SCREEN_MODULES = (
    {
        'code': 'attendance_screen_devices',
        'name': 'الحضور — أجهزة البصمة',
        'perm': ATTENDANCE_SCREEN_DEVICES_VIEW,
        'order': 111,
    },
    {
        'code': 'attendance_screen_report',
        'name': 'الحضور — تقرير البصمة',
        'perm': ATTENDANCE_SCREEN_REPORT_VIEW,
        'order': 112,
    },
    {
        'code': 'attendance_screen_late_alerts',
        'name': 'الحضور — إنذار تأخير البصمة',
        'perm': ATTENDANCE_SCREEN_LATE_ALERTS_VIEW,
        'order': 113,
    },
    {
        'code': 'attendance_screen_records',
        'name': 'الحضور — سجلات الحضور',
        'perm': ATTENDANCE_SCREEN_RECORDS_VIEW,
        'order': 114,
    },
)


def register_attendance_sub_permissions() -> None:
    """تسجيل وحدات الشاشات الفرعية في permissions_registry."""
    for screen in _SCREEN_MODULES:
        register_module(
            screen['code'],
            name=screen['name'],
            icon='fingerprint',
            order=screen['order'],
        )
        register_permission(screen['perm'])


def expand_attendance_sub_permissions(codes: set[str]) -> set[str]:
    """attendance.view تمنح كل شاشات العرض الفرعية."""
    expanded = set(codes)
    if 'attendance.view' in expanded:
        expanded |= ATTENDANCE_SCREEN_VIEW_CODES
    return expanded


def user_has_attendance_nav(user) -> bool:
    """هل يظهر قسم الحضور والبصمة في الشريط الجانبي؟"""
    from apps.core.decorators import get_user_permissions

    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    perms = get_user_permissions(user)
    prefixes = ('attendance.', 'attendance_screen_')
    return any(any(p.startswith(pref) for pref in prefixes) for p in perms)
