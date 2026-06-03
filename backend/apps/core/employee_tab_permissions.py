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
    {'key': 'trips', 'label': 'رحلات العمل', 'order': 137},
    {'key': 'contract', 'label': 'العقد', 'order': 138},
    {'key': 'loans', 'label': 'السلف', 'order': 139},
    {'key': 'absences', 'label': 'الغيابات', 'order': 140},
    {'key': 'fingerprint', 'label': 'البصمة', 'order': 141},
    {'key': 'docs', 'label': 'المستندات', 'order': 142},
    {'key': 'accruals', 'label': 'المخصصات والأرصدة', 'order': 143},
    {'key': 'archive', 'label': 'أرشيف الحركة', 'order': 144},
    {'key': 'termination', 'label': 'التصفيات', 'order': 145},
)

TAB_KEYS = tuple(t['key'] for t in EMPLOYEE_TABS)

# تبويبات نموذج التعديل (أقل من صفحة العرض)
EDIT_FORM_TAB_KEYS = frozenset({
    'main', 'contract', 'salary', 'leaves', 'schedule', 'warnings', 'docs', 'archive',
})


def tab_permission_code(tab_key: str) -> str:
    return f'employee_tab_{tab_key}.view'


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


def employee_tab_visibility(user) -> dict[str, bool]:
    return {key: user_can_see_employee_tab(user, key) for key in TAB_KEYS}


def resolve_default_employee_tab(
    user,
    requested: str | None = None,
    *,
    allowed_keys: tuple[str, ...] | None = None,
) -> str:
    """أول تبويب مسموح — أو المطلوب إن كان مسموحاً."""
    visible = employee_tab_visibility(user)
    keys = allowed_keys or TAB_KEYS
    if requested and requested in keys and visible.get(requested):
        return requested
    for tab in EMPLOYEE_TABS:
        if tab['key'] in keys and visible.get(tab['key']):
            return tab['key']
    return 'main'


def employee_tab_nav_for_user(user, *, keys: tuple[str, ...] | None = None) -> list[dict]:
    visible = employee_tab_visibility(user)
    tabs = EMPLOYEE_TABS
    if keys is not None:
        allowed = frozenset(keys)
        tabs = [t for t in EMPLOYEE_TABS if t['key'] in allowed]
    return [
        {**tab, 'visible': visible.get(tab['key'], False)}
        for tab in tabs
    ]


def enrich_employee_page_context(
    user,
    context: dict,
    *,
    requested_tab: str | None = None,
    edit_form: bool = False,
) -> dict:
    context['tab_visible'] = employee_tab_visibility(user)
    context['can_view_salary'] = user_can_view_salary(user)
    context['can_edit_salary'] = user_can_edit_salary(user)
    nav_keys = EDIT_FORM_TAB_KEYS if edit_form else None
    context['employee_tab_nav'] = employee_tab_nav_for_user(user, keys=nav_keys)
    allowed = tuple(nav_keys) if nav_keys else TAB_KEYS
    context['default_employee_tab'] = resolve_default_employee_tab(user, requested_tab, allowed_keys=allowed)
    return context
