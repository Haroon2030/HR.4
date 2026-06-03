"""
سياسات الصلاحيات المركزية — ربط القوائم والتقارير والنماذج بصلاحيات DB.
"""
from __future__ import annotations

from apps.core.decorators import get_user_permissions, has_permission, _is_super_or_admin
from apps.core.salary_access import user_can_edit_salary, user_can_view_salary

# تقارير تحتوي بيانات رواتب
# تقارير تُظهر رواتب أو مبالغ مالية للموظفين
SALARY_REPORT_KEYS_STRICT = frozenset({
    'branches',
    'cost_centers_overview',
    'salary_expenses',
    'allowances_breakdown',
    'deductions_breakdown',
    'terminations',
    'professions',
})

HR_FORMS_WITH_SALARY = frozenset({
    'employment_letter',
    'salary_adjustment',
})


def user_can_view_financial_reports(user) -> bool:
    """تقارير الرواتب والمصاريف."""
    if _is_super_or_admin(user):
        return True
    return (
        user_can_view_salary(user)
        or has_permission(user, 'payroll.view_reports')
        or has_permission(user, 'reports.view_all')
    )


def report_allowed_for_user(user, report_key: str) -> bool:
    if report_key not in SALARY_REPORT_KEYS_STRICT:
        return True
    if not user_can_view_financial_reports(user):
        return False
    if report_key == 'deductions_breakdown':
        return _any_perm(user, 'payroll.view', 'payroll.view_reports', 'payroll.process', 'payroll.manage')
    return True


def hr_form_allowed_for_user(user, form_key: str) -> bool:
    if form_key not in HR_FORMS_WITH_SALARY:
        return True
    return user_can_view_salary(user)


def _any_perm(user, *codes: str) -> bool:
    if _is_super_or_admin(user):
        return True
    perms = get_user_permissions(user)
    return any(c in perms for c in codes)


def org_structure_permissions(user) -> dict[str, bool]:
    """أزرار الكتابة في شاشة تهيئة النظام (الفروع + بيانات النظام)."""
    return {
        'branch_write': _any_perm(
            user, 'branches.add', 'branches.edit', 'branches.manage',
        ),
        'branch_edit': _any_perm(user, 'branches.edit', 'branches.manage'),
        'branch_delete': _any_perm(user, 'branches.delete', 'branches.manage'),
        'cost_center_write': _any_perm(user, 'cost_centers.add', 'cost_centers.edit'),
        'cost_center_edit': _any_perm(user, 'cost_centers.edit'),
        'cost_center_delete': _any_perm(user, 'cost_centers.delete'),
        'department_write': _any_perm(
            user, 'departments.add', 'departments.edit', 'departments.manage',
        ),
        'department_edit': _any_perm(user, 'departments.edit', 'departments.manage'),
        'department_delete': _any_perm(user, 'departments.delete', 'departments.manage'),
        'system_data_add': _any_perm(user, 'system_data.add'),
        'system_data_edit': _any_perm(user, 'system_data.edit'),
        'system_data_delete': _any_perm(user, 'system_data.delete'),
    }
