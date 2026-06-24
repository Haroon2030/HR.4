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
from apps.employees.services.migration_balance import (
    compute_opening_leave_days,
    compute_period_leave_accrual_days,
    employee_leave_accrual_start,
    employee_uses_migration_balance,
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
    الرصيد المستحق:
    - عند وجود تاريخ احتساب: افتتاحي + تراكم من تاريخ الاحتساب
    - وإلا: من تاريخ المباشرة حتى اليوم
    """
    if not employee.sponsorship_id:
        return Decimal('0.00')

    end = employee_as_of_date(employee, as_of=as_of)

    if employee_uses_migration_balance(employee):
        opening = compute_opening_leave_days(employee)
        period = compute_period_leave_accrual_days(employee, as_of=end)
        return (opening + period).quantize(LEAVE_DAYS_QUANT)

    if not employee.hire_date:
        return Decimal('0.00')
    return accrued_annual_leave_days(employee.hire_date, end)


def sum_annual_leave_days_taken(employee, *, since: date | None = None) -> Decimal:
    """مجموع أيام الإجازات السنوية المُسجَّلة في النظام."""
    from apps.employees.models import EmployeeLeave

    qs = EmployeeLeave.objects.filter(
        employee_id=employee.pk,
        leave_type=EmployeeLeave.LeaveType.ANNUAL,
    )
    if since:
        qs = qs.filter(date_from__gte=since)
    total = qs.aggregate(total=Sum('days'))['total']
    return Decimal(total or 0).quantize(LEAVE_DAYS_QUANT)


def resolve_used_leave_days(employee) -> Decimal:
    """
    أيام الإجازة المستخدمة:
    - عند وجود تاريخ احتساب: إجازات سنوية من ذلك التاريخ فصاعداً
    - وإلا: سجلات الإجازة أو الحقل اليدوي available_leave_balance
    """
    from apps.employees.models import EmployeeLeave

    if employee_uses_migration_balance(employee):
        start = employee_leave_accrual_start(employee)
        if start:
            return sum_annual_leave_days_taken(employee, since=start)
        return Decimal('0.00')

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


def leave_balance_breakdown(employee, *, as_of: date | None = None) -> dict:
    """تفصيل الرصيد للعرض في الواجهة."""
    end = employee_as_of_date(employee, as_of=as_of)
    uses_migration = employee_uses_migration_balance(employee)
    opening = compute_opening_leave_days(employee) if uses_migration else Decimal('0.00')
    period_accrual = (
        compute_period_leave_accrual_days(employee, as_of=end)
        if uses_migration
        else Decimal('0.00')
    )
    if not uses_migration and employee.hire_date and employee.sponsorship_id:
        period_accrual = accrued_annual_leave_days(employee.hire_date, end)

    total = compute_employee_accrued_leave_days(employee, as_of=end)
    used = resolve_used_leave_days(employee)
    remaining = compute_employee_remaining_leave_days(employee, as_of=end)

    return {
        'uses_migration': uses_migration,
        'opening_days': opening,
        'period_accrual_days': period_accrual,
        'total_accrued': total,
        'used_days': used,
        'remaining_days': remaining,
        'leave_accrual_start': employee_leave_accrual_start(employee),
        'hire_date': getattr(employee, 'hire_date', None),
        'as_of': end,
    }


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

    end = as_of or employee_as_of_date(employee)
    used = resolve_used_leave_days(employee)

    if employee_uses_migration_balance(employee):
        opening = compute_opening_leave_days(employee)
        period = compute_period_leave_accrual_days(employee, as_of=end, flat_21_only=flat_21_only)
        accrued = (opening + period).quantize(LEAVE_DAYS_QUANT)
        accrual_start = employee_leave_accrual_start(employee)
        months = (
            completed_employment_months(accrual_start, end)
            if accrual_start
            else 0
        )
        rule = leave_accrual_formula_label(flat_21_only=flat_21_only, months=months)
        prefix = f'{title} — ' if title else ''
        remaining = (accrued - used).quantize(LEAVE_DAYS_QUANT)
        if remaining < 0:
            remaining = Decimal('0.00')
        daily = daily_rate_from_total(employee.total_salary)
        amount = (remaining * daily).quantize(Decimal('0.01'))
        text = (
            f'{prefix}رصيد إجازات (افتتاحي + تراكم)\n'
            f'رصيد افتتاحي: {opening} يوم\n'
            f'تراكم من {accrual_start or "—"}: {period} يوم\n'
            f'قاعدة التراكم: {rule}\n'
            f'المستحق: {accrued} يوم − المستخدم: {used} = {remaining} يوم\n'
            f'أجر اليوم: الراتب ÷ 30 = {daily} ر.س\n'
            f'رصيد الإجازة: {remaining} يوم × {daily} = {amount} ر.س\n'
            f'مكافأة نهاية الخدمة تُحسب من تاريخ المباشرة: {employee.hire_date or "—"}'
        )
        return accrued, used, remaining, amount, text

    if not employee.hire_date:
        return Decimal('0'), used, Decimal('0'), Decimal('0'), 'لا يوجد تاريخ مباشرة — لم يُحسب رصيد الإجازة'

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
