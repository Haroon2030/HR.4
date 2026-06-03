"""
التحكم في عرض/تعديل بيانات الرواتب (ملف الموظف + مسير الرواتب).
"""
from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from apps.core.decorators import has_permission, _is_super_or_admin

# حقول الراتب في EmployeeForm
EMPLOYEE_SALARY_FIELD_NAMES = (
    'basic_salary',
    'housing_allowance',
    'transport_allowance',
    'other_allowance',
    'cash_amount',
    'meal_allowance',
    'insurance_deduction_rate',
    'bank',
    'iban',
)

PAYROLL_MANAGE_CODES = ('payroll.manage', 'payroll.process', 'payroll.edit')


def user_can_view_salary(user) -> bool:
    """عرض تبويب الراتب / مبالغ الرواتب في ملف الموظف أو مسير الرواتب."""
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    if _is_super_or_admin(user):
        return True
    return (
        has_permission(user, 'employees.view_salary')
        or has_permission(user, 'payroll.view')
    )


def user_can_edit_salary(user) -> bool:
    """تعديل حقول الراتب أو بناء/ترحيل مسير."""
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return False
    if _is_super_or_admin(user):
        return True
    if has_permission(user, 'employees.edit_salary'):
        return True
    return any(has_permission(user, code) for code in PAYROLL_MANAGE_CODES)


def user_can_manage_payroll(user) -> bool:
    """بناء / إعادة بناء / ترحيل مسير الرواتب."""
    return user_can_edit_salary(user)


def salary_view_required(view_func):
    """يمنع إجراءات تحتوي مبالغ رواتب/مكافأة نهاية خدمة بدون صلاحية عرض الراتب."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            from urllib.parse import urlencode
            login = settings.LOGIN_URL
            return redirect(f'{login}?{urlencode({"next": request.get_full_path()})}')
        if not user_can_view_salary(request.user):
            messages.error(request, 'لا تملك صلاحية عرض بيانات الرواتب لهذا الإجراء.')
            return redirect('web:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper
