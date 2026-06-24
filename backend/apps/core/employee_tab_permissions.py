"""
صلاحيات تبويبات ملف الموظف — وحدة مستقلة لكل تبويب (employee_tab_<key>.view).

إن لم يُمنح المستخدم أي صلاحية تبويب، يُعتمد على employees.view (توافق مع التثبيتات القديمة).
"""
from __future__ import annotations

from apps.core.decorators import get_user_permissions, _is_super_or_admin
from apps.core.permissions_registry import register_module, register_permission
from apps.core.salary_access import user_can_edit_salary, user_can_view_salary

# تبويبات حساسة مالياً — لا تُعرض بمجرد employees.view
_SALARY_SENSITIVE_TAB_KEYS = frozenset({'salary', 'accruals'})

# ترتيب العرض في صفحة الموظف
EMPLOYEE_TABS = (
    {'key': 'main', 'label': 'بيانات الموظف', 'order': 131},
    {'key': 'salary', 'label': 'الراتب', 'order': 132},
    {'key': 'leaves', 'label': 'الإجازات', 'order': 133},
    {'key': 'schedule', 'label': 'الجدول', 'order': 134},
    {'key': 'warnings', 'label': 'الإفادات والإنذارات', 'order': 135},
    {'key': 'custodies', 'label': 'العهد', 'order': 136},
    {'key': 'contract', 'label': 'العقد', 'order': 138},
    {'key': 'loans', 'label': 'السلف', 'order': 139},
    {'key': 'absences', 'label': 'الغيابات', 'order': 140},
    {'key': 'cash_shortages', 'label': 'العجوزات', 'order': 141},
    {'key': 'fingerprint', 'label': 'البصمة', 'order': 142},
    {'key': 'docs', 'label': 'المستندات', 'order': 143},
    {'key': 'accruals', 'label': 'المخصصات والأرصدة', 'order': 144},
    {'key': 'archive', 'label': 'أرشيف الحركة', 'order': 145},
    {'key': 'termination', 'label': 'التصفيات', 'order': 146},
)

TAB_KEYS = tuple(t['key'] for t in EMPLOYEE_TABS)

# عملية تصفية نهاية خدمة / استقالة — صلاحية مستقلة (افتراضياً: أدمن + مدير الموارد)
SETTLEMENT_EXECUTE_PERMISSION = 'employee_tab_termination.execute'

# تبويبات نموذج التعديل — بيانات أساسية فقط (العمليات من شاشة العرض)
EDIT_FORM_TAB_KEYS = frozenset({
    'main', 'contract', 'salary', 'leaves', 'schedule', 'docs',
})


def tab_permission_code(tab_key: str) -> str:
    return f'employee_tab_{tab_key}.view'


def settlement_execute_permission_code() -> str:
    return SETTLEMENT_EXECUTE_PERMISSION


def register_employee_tab_permissions() -> None:
    """تسجيل وحدات التبويبات في permissions_registry (تُزامَن مع DB عند migrate)."""
    for tab in EMPLOYEE_TABS:
        module_code = f'employee_tab_{tab["key"]}'
        register_module(
            module_code,
            name=f'تبويب — {tab["label"]}',
            icon='layout-grid',
            order=tab['order'],
        )
        register_permission(tab_permission_code(tab['key']))
        if tab['key'] == 'termination':
            register_permission(SETTLEMENT_EXECUTE_PERMISSION)


def _user_has_any_tab_permission(user) -> bool:
    perms = get_user_permissions(user)
    return any(p.startswith('employee_tab_') and p.endswith('.view') for p in perms)


def user_can_see_employee_tab(user, tab_key: str) -> bool:
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    if _is_super_or_admin(user):
        return True
    if tab_key not in TAB_KEYS:
        return False
    code = tab_permission_code(tab_key)
    perms = get_user_permissions(user)
    if not _user_has_any_tab_permission(user):
        if tab_key in _SALARY_SENSITIVE_TAB_KEYS:
            return user_can_view_salary(user)
        return 'employees.view' in perms
    return code in perms


def user_can_execute_settlement(user) -> bool:
    """تقديم طلب تصفية نهاية خدمة / استقالة — افتراضياً أدمن ومدير الموارد، أو منح صريح."""
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    from apps.core.decorators import has_permission

    return has_permission(user, SETTLEMENT_EXECUTE_PERMISSION)


def employee_tab_visibility(user) -> dict[str, bool]:
    return {key: user_can_see_employee_tab(user, key) for key in TAB_KEYS}


def resolve_default_employee_tab(
    user,
    requested: str | None = None,
    *,
    allowed_keys: tuple[str, ...] | None = None,
    visible: dict[str, bool] | None = None,
) -> str:
    """أول تبويب مسموح — أو المطلوب إن كان مسموحاً."""
    visible = visible if visible is not None else employee_tab_visibility(user)
    keys = allowed_keys or TAB_KEYS
    if requested and requested in keys and visible.get(requested):
        return requested
    for tab in EMPLOYEE_TABS:
        if tab['key'] in keys and visible.get(tab['key']):
            return tab['key']
    return 'main'


def employee_tab_nav_for_user(
    user,
    *,
    keys: tuple[str, ...] | None = None,
    visible: dict[str, bool] | None = None,
) -> list[dict]:
    visible = visible if visible is not None else employee_tab_visibility(user)
    tabs = EMPLOYEE_TABS
    if keys is not None:
        allowed = frozenset(keys)
        tabs = [t for t in EMPLOYEE_TABS if t['key'] in allowed]
    return [
        {**tab, 'visible': visible.get(tab['key'], False)}
        for tab in tabs
    ]


def _user_can_edit_employee_record(user, specific_code: str) -> bool:
    from apps.core.decorators import has_permission

    return (
        has_permission(user, specific_code)
        or has_permission(user, 'employees.edit')
    )


def _user_can_delete_employee_record(user, delete_code: str, edit_code: str) -> bool:
    from apps.core.decorators import has_permission

    return (
        has_permission(user, delete_code)
        or has_permission(user, 'employees.delete')
        or has_permission(user, edit_code)
        or has_permission(user, 'employees.edit')
    )


def enrich_employee_page_context(
    user,
    context: dict,
    *,
    requested_tab: str | None = None,
    edit_form: bool = False,
) -> dict:
    from django.conf import settings

    tab_visible = employee_tab_visibility(user)
    context['tab_visible'] = tab_visible
    context['can_view_salary'] = user_can_view_salary(user)
    context['can_edit_salary'] = user_can_edit_salary(user)
    context['can_execute_settlement'] = user_can_execute_settlement(user)
    from apps.core.decorators import has_permission
    context['can_edit_leave_settings'] = has_permission(user, 'employees.edit')
    context['can_edit_leave'] = _user_can_edit_employee_record(user, 'employees.edit_leave')
    context['can_delete_leave'] = _user_can_delete_employee_record(
        user, 'employees.delete_leave', 'employees.edit_leave',
    )
    context['can_edit_absence'] = _user_can_edit_employee_record(user, 'employees.edit_absence')
    context['can_delete_absence'] = _user_can_delete_employee_record(
        user, 'employees.delete_absence', 'employees.edit_absence',
    )
    context['can_edit_statement'] = _user_can_edit_employee_record(user, 'employees.edit_statement')
    context['can_delete_statement'] = _user_can_delete_employee_record(
        user, 'employees.delete_statement', 'employees.edit_statement',
    )
    context['can_edit_loan'] = _user_can_edit_employee_record(user, 'employees.edit_loan')
    context['can_delete_loan'] = _user_can_delete_employee_record(
        user, 'employees.delete_loan', 'employees.edit_loan',
    )
    context['can_edit_ledger'] = _user_can_edit_employee_record(user, 'employees.edit_ledger')
    context['can_delete_ledger'] = _user_can_delete_employee_record(
        user, 'employees.delete_ledger', 'employees.edit_ledger',
    )
    context['hr_notification_email'] = (
        getattr(settings, 'HR_NOTIFICATION_EMAIL', '') or ''
    )
    nav_keys = EDIT_FORM_TAB_KEYS if edit_form else None
    context['employee_tab_nav'] = employee_tab_nav_for_user(
        user, keys=nav_keys, visible=tab_visible,
    )
    allowed = tuple(nav_keys) if nav_keys else TAB_KEYS
    context['default_employee_tab'] = resolve_default_employee_tab(
        user, requested_tab, allowed_keys=allowed, visible=tab_visible,
    )
    return context
