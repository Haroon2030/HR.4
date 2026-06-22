"""حساب رصيد الإجازات — موحّد بين تبويب الإجازات والتصفية والمخصصات."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.core.salary_month import (
    accrued_annual_leave_days,
    completed_employment_months,
    daily_rate_from_total,
    employment_service_days,
    leave_accrual_formula_label,
    LEAVE_DAYS_QUANT,
)


def employee_as_of_date(employee, *, as_of: date | None = None) -> date:
    """تاريخ احتساب الرصيد: نهاية الخدمة أو التاريخ المطلوب أو اليوم."""
    return getattr(employee, 'end_date', None) or as_of or timezone.localdate()


def employee_service_days(employee, *, as_of: date | None = None) -> int:
    """أيام الخدمة من تاريخ المباشرة حتى تاريخ التصفية أو اليوم."""
    hire = getattr(employee, 'hire_date', None)
    if not hire:
        return 0
    return employment_service_days(hire, employee_as_of_date(employee, as_of=as_of))


def compute_employee_accrued_leave_days(employee, *, as_of: date | None = None) -> Decimal:
    """
    الرصيد المستحق — دائماً من القاعدة الموحدة (شهر = 30 يوماً، 1.75 يوم/شهر).
    لا يعتمد على دفتر المخصصات لتجنب اختلاف التراكم مع العرض.
    """
    if not employee.hire_date or not employee.sponsorship_id:
        return Decimal('0.00')
    end = employee_as_of_date(employee, as_of=as_of)
    return accrued_annual_leave_days(employee.hire_date, end)


def sum_annual_leave_days_taken(employee) -> Decimal:
    """مجموع أيام الإجازات السنوية المُسجَّلة في النظام."""
    from apps.employees.models import EmployeeLeave

    total = (
        EmployeeLeave.objects.filter(
            employee_id=employee.pk,
            leave_type=EmployeeLeave.LeaveType.ANNUAL,
        ).aggregate(total=Sum('days'))['total']
    )
    return Decimal(total or 0).quantize(LEAVE_DAYS_QUANT)


def resolve_used_leave_days(employee) -> Decimal:
    """
    أيام الإجازة المستخدمة:
    - إن وُجدت سجلات إجازة سنوية → المجموع من السجلات (مصدر الحقيقة)
    - وإلا → الحقل اليدوي available_leave_balance (تراث/إدخال يدوي)
    """
    from apps.employees.models import EmployeeLeave

    stored = Decimal(employee.available_leave_balance or 0).quantize(LEAVE_DAYS_QUANT)
    has_annual = EmployeeLeave.objects.filter(
        employee_id=employee.pk,
        leave_type=EmployeeLeave.LeaveType.ANNUAL,
    ).exists()
    if has_annual:
        return sum_annual_leave_days_taken(employee)
    return stored


def compute_employee_remaining_leave_days(employee, *, as_of: date | None = None) -> Decimal:
    """المتبقي = المستحق − المستخدم."""
    accrued = compute_employee_accrued_leave_days(employee, as_of=as_of)
    used = resolve_used_leave_days(employee)
    remaining = (accrued - used).quantize(LEAVE_DAYS_QUANT)
    if remaining < 0:
        return Decimal('0.00')
    return remaining


def settlement_leave_for_employee(
    employee,
    *,
    as_of: date | None = None,
    flat_21_only: bool = False,
    title: str = '',
) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
    """
    رصيد الإجازة عند التصفية — نفس قاعدة الشهر 30 يوم لكل الأنواع.
    Returns: (accrued, used, remaining, amount, descriptive_text)
    """
    if not employee.sponsorship_id:
        return (
            Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'),
            'لا يوجد كفالة — لم تُحتسب مستحقات الإجازة',
        )

    if not employee.hire_date:
        used = resolve_used_leave_days(employee)
        return Decimal('0'), used, Decimal('0'), Decimal('0'), 'لا يوجد تاريخ مباشرة — لم يُحسب رصيد الإجازة'

    end = as_of or employee_as_of_date(employee)
    used = resolve_used_leave_days(employee)
    months = completed_employment_months(employee.hire_date, end)
    accrued = accrued_annual_leave_days(employee.hire_date, end, flat_21_only=flat_21_only)
    remaining = (accrued - used).quantize(LEAVE_DAYS_QUANT)
    if remaining < 0:
        remaining = Decimal('0.00')

    daily = daily_rate_from_total(employee.total_salary)
    amount = (remaining * daily).quantize(Decimal('0.01'))
    rule = leave_accrual_formula_label(flat_21_only=flat_21_only, months=months)
    prefix = f'{title} — ' if title else ''
    from apps.core.salary_month import MONTHLY_LEAVE_ACCRUAL_DAYS, MONTHLY_LEAVE_AFTER_FIVE_YEARS
    rate = MONTHLY_LEAVE_ACCRUAL_DAYS if (flat_21_only or months <= 60) else MONTHLY_LEAVE_AFTER_FIVE_YEARS
    text = (
        f'{prefix}رصيد إجازات\n'
        f'قاعدة الاستحقاق: {rule}\n'
        f'أشهر الخدمة المكتملة: {months} (معدل {rate} يوم/شهر)\n'
        f'المستحق: {accrued} يوم − المستخدم: {used} = {remaining} يوم\n'
        f'أجر اليوم: الراتب ÷ 30 = {daily} ر.س\n'
        f'رصيد الإجازة: {remaining} يوم × {daily} = {amount} ر.س'
    )
    return accrued, used, remaining, amount, text
