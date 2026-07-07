"""
شاشات فرعية لإدارة الصيانة — وحدة مستقلة لكل شاشة في مصفوفة الصلاحيات.

الصلاحيات الجديدة (maintenance_screen_*.view / maintenance_setup.*) تُوسَّع تلقائياً
إلى أكواد maintenance.* الحالية. أكواد maintenance.* الأصلية تُوسَّع إلى شاشاتها
لتمكين منع شاشة فرعية مع الاحتفاظ بصلاحيات أخرى.
"""
from __future__ import annotations

from apps.core.permissions_registry import register_module, register_permission

MAINTENANCE_SCREEN_REQUESTS_VIEW = 'maintenance_screen_requests.view'
MAINTENANCE_SCREEN_REQUEST_ADD_VIEW = 'maintenance_screen_request_add.view'
MAINTENANCE_SCREEN_ASSIGN_VIEW = 'maintenance_screen_assign.view'
MAINTENANCE_SCREEN_MANAGER_CLOSE_VIEW = 'maintenance_screen_manager_close.view'
MAINTENANCE_SCREEN_BRANCH_CONFIRM_VIEW = 'maintenance_screen_branch_confirm.view'
MAINTENANCE_SCREEN_RETURN_VIEW = 'maintenance_screen_return.view'

MAINTENANCE_SETUP_VIEW = 'maintenance_setup.view'
MAINTENANCE_SETUP_ADD = 'maintenance_setup.add'
MAINTENANCE_SETUP_EDIT = 'maintenance_setup.edit'
MAINTENANCE_SETUP_DELETE = 'maintenance_setup.delete'

MAINTENANCE_SCREEN_VIEW_CODES: frozenset[str] = frozenset({
    MAINTENANCE_SCREEN_REQUESTS_VIEW,
    MAINTENANCE_SCREEN_REQUEST_ADD_VIEW,
    MAINTENANCE_SCREEN_ASSIGN_VIEW,
    MAINTENANCE_SCREEN_MANAGER_CLOSE_VIEW,
    MAINTENANCE_SCREEN_BRANCH_CONFIRM_VIEW,
    MAINTENANCE_SCREEN_RETURN_VIEW,
})

MAINTENANCE_NAV_SCREEN_CODES: frozenset[str] = frozenset({
    MAINTENANCE_SCREEN_REQUESTS_VIEW,
    MAINTENANCE_SCREEN_REQUEST_ADD_VIEW,
    MAINTENANCE_SETUP_VIEW,
})

_SCREEN_MODULES = (
    {
        'code': 'maintenance_screen_requests',
        'name': 'صيانة — طلبات الصيانة',
        'legacy': 'maintenance.view',
        'order': 141,
    },
    {
        'code': 'maintenance_screen_request_add',
        'name': 'صيانة — طلب سريع',
        'legacy': 'maintenance.add',
        'order': 142,
    },
    {
        'code': 'maintenance_screen_assign',
        'name': 'صيانة — إسناد الطلبات',
        'legacy': 'maintenance.assign',
        'order': 143,
    },
    {
        'code': 'maintenance_screen_manager_close',
        'name': 'صيانة — إغلاق مدير الصيانة',
        'legacy': 'maintenance.manage',
        'order': 144,
    },
    {
        'code': 'maintenance_screen_branch_confirm',
        'name': 'صيانة — تأكيد الفرع',
        'legacy': 'maintenance.confirm_branch',
        'order': 145,
    },
    {
        'code': 'maintenance_screen_return',
        'name': 'صيانة — إرجاع الطلب',
        'legacy': 'maintenance.return',
        'order': 146,
    },
)

_SETUP_MODULE = {
    'code': 'maintenance_setup',
    'name': 'صيانة — تهيئة',
    'order': 147,
    'ops': {
        'view': 'maintenance.workers_view',
        'add': 'maintenance.workers_add',
        'edit': 'maintenance.workers_edit',
        'delete': 'maintenance.workers_delete',
    },
}

SUB_TO_LEGACY: dict[str, str] = {}

_LEGACY_TO_SCREEN: dict[str, str] = {
    screen['legacy']: f"{screen['code']}.view" for screen in _SCREEN_MODULES
}

_SETUP_LEGACY_TO_SCREEN: dict[str, str] = {
    legacy: f"{_SETUP_MODULE['code']}.{op}"
    for op, legacy in _SETUP_MODULE['ops'].items()
}


def register_maintenance_sub_permissions() -> None:
    """تسجيل وحدات الشاشات الفرعية في permissions_registry."""
    SUB_TO_LEGACY.clear()
    for screen in _SCREEN_MODULES:
        register_module(
            screen['code'],
            name=screen['name'],
            icon='wrench',
            order=screen['order'],
        )
        perm_code = f"{screen['code']}.view"
        register_permission(perm_code)
        SUB_TO_LEGACY[perm_code] = screen['legacy']

    setup = _SETUP_MODULE
    register_module(setup['code'], name=setup['name'], icon='settings-2', order=setup['order'])
    for op, legacy in setup['ops'].items():
        perm_code = f"{setup['code']}.{op}"
        register_permission(perm_code)
        SUB_TO_LEGACY[perm_code] = legacy


def expand_maintenance_sub_permissions(codes: set[str]) -> set[str]:
    """شاشة → legacy، و legacy أصلي → شاشة (للتوافق مع الأدوار الحالية)."""
    expanded = set(codes)
    for sub_code, legacy_code in SUB_TO_LEGACY.items():
        if sub_code in expanded:
            expanded.add(legacy_code)
    for legacy_code, screen_code in _LEGACY_TO_SCREEN.items():
        if legacy_code in expanded:
            expanded.add(screen_code)
    for legacy_code, screen_code in _SETUP_LEGACY_TO_SCREEN.items():
        if legacy_code in expanded:
            expanded.add(screen_code)
    return expanded


def user_has_maintenance_nav(user) -> bool:
    """هل يظهر قسم الصيانة في الشريط الجانبي؟"""
    from apps.core.decorators import has_permission

    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    return any(has_permission(user, code) for code in MAINTENANCE_NAV_SCREEN_CODES)
