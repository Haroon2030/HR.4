"""حساب رصيد الإجازات — موحّد بين تبويب الإجازات والتصفية والمخصصات."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.employees.services.accrual_ledger_notes import MONTHLY_LEAVE_ACCRUAL_DAYS
from apps.employees.services.settlement_eosb import (
    LEAVE_DAYS_AFTER_FIVE_YEARS,
    LEAVE_DAYS_FIRST_FIVE_YEARS,
)

LEAVE_DAYS_QUANT = Decimal('0.01')
FIRST_FIVE_YEARS_MONTHS = 60
MONTHLY_LEAVE_AFTER_FIVE_YEARS = LEAVE_DAYS_AFTER_FIVE_YEARS / Decimal('12')  # 2.5 يوم/شهر


def employee_as_of_date(employee, *, as_of: date | None = None) -> date:
    """تاريخ احتساب الرصيد: نهاية الخدمة أو التاريخ المطلوب أو اليوم."""
    return getattr(employee, 'end_date', None) or as_of or timezone.localdate()


def employee_service_days(employee, *, as_of: date | None = None) -> int:
    """أيام الخدمة من تاريخ المباشرة حتى تاريخ التصفية أو اليوم."""
    hire = getattr(employee, 'hire_date', None)
    if not hire:
        return 0
    end = employee_as_of_date(employee, as_of=as_of)
    days = (end - hire).days
    return max(days, 0)


def completed_service_months(hire_date: date, as_of: date) -> int:
    """أشهر الخدمة المكتملة — نفس منطق الاستحقاق الشهري (1.75 يوم/شهر)."""
    if as_of < hire_date:
        return 0
    months = (as_of.year - hire_date.year) * 12 + (as_of.month - hire_date.month)
    if as_of.day < hire_date.day:
        months -= 1
    return max(months, 0)


def compute_monthly_tiered_leave_accrued_days(service_months: int) -> Decimal:
    """
    21 يوم/سنة = 1.75 يوم/شهر (أول 5 سنوات)، 30 يوم/سنة = 2.5 يوم/شهر بعدها.
    يطابق مسير الرواتب وسجل المخصصات.
    """
    if service_months <= 0:
        return Decimal('0.00')
    if service_months <= FIRST_FIVE_YEARS_MONTHS:
        return (Decimal(service_months) * MONTHLY_LEAVE_ACCRUAL_DAYS).quantize(LEAVE_DAYS_QUANT)
    first_5_leave = LEAVE_DAYS_FIRST_FIVE_YEARS * Decimal('5')
    extra_months = service_months - FIRST_FIVE_YEARS_MONTHS
    extra = (Decimal(extra_months) * MONTHLY_LEAVE_AFTER_FIVE_YEARS).quantize(LEAVE_DAYS_QUANT)
    return (first_5_leave + extra).quantize(LEAVE_DAYS_QUANT)


def _gross_accrued_from_ledger(employee) -> Decimal | None:
    """إجمالي المستحق من الدفتر = الرصيد التراكمي + المستخدم."""
    from apps.employees.services.ledger_balances import get_latest_ledger_balance

    last = get_latest_ledger_balance(employee)
    if last is None:
        return None
    net = Decimal(last.cumulative_leave_days or 0).quantize(LEAVE_DAYS_QUANT)
    used = resolve_used_leave_days(employee)
    return (net + used).quantize(LEAVE_DAYS_QUANT)


def compute_employee_accrued_leave_days(employee, *, as_of: date | None = None) -> Decimal:
    """
    الرصيد المستحق:
    - مع سجل مخصصات: إجمالي التراكم من الدفتر + المستخدم
    - بدون دفتر: أشهر الخدمة المكتملة × 1.75 (أو 2.5 بعد 5 سنوات)
    """
    if not employee.hire_date or not employee.sponsorship_id:
        return Decimal('0.00')

    from_ledger = _gross_accrued_from_ledger(employee)
    if from_ledger is not None:
        return from_ledger

    end = employee_as_of_date(employee, as_of=as_of)
    months = completed_service_months(employee.hire_date, end)
    if months <= 0:
        return Decimal('0.00')
    return compute_monthly_tiered_leave_accrued_days(months)


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
    """المتبقي — من الدفتر إن وُجد، وإلا المستحق − المستخدم."""
    _, _, remaining, _, _ = settlement_leave_for_employee(employee, as_of=as_of)
    return remaining


def settlement_leave_for_employee(
    employee,
    *,
    as_of: date | None = None,
    flat_21_only: bool = False,
    title: str = '',
) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
    """
    رصيد الإجازة عند التصفية — موحّد لكل أنواع التصفية.
    Returns: (accrued, used, remaining, amount, descriptive_text)
    """
    from apps.core.salary_month import daily_rate_from_total
    from apps.employees.services.ledger_balances import get_latest_ledger_balance

    if not employee.sponsorship_id:
        return Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'), 'لا يوجد كفالة — لم تُحتسب مستحقات الإجازة'

    used = resolve_used_leave_days(employee)
    end = as_of or employee_as_of_date(employee)

    if not flat_21_only:
        last = get_latest_ledger_balance(employee)
        if last is not None:
            remaining = Decimal(last.cumulative_leave_days or 0).quantize(LEAVE_DAYS_QUANT)
            if remaining < 0:
                remaining = Decimal('0.00')
            accrued = (remaining + used).quantize(LEAVE_DAYS_QUANT)
            amount = Decimal(last.cumulative_leave_amount or 0).quantize(Decimal('0.01'))
            daily = daily_rate_from_total(employee.total_salary)
            if amount <= 0 and remaining > 0:
                amount = (remaining * daily).quantize(Decimal('0.01'))
            prefix = f'{title} — ' if title else ''
            text = (
                f'{prefix}رصيد الدفتر: {remaining} يوم '
                f'(مستحق {accrued} − مستخدم {used})\n'
                f'قيمة الإجازة: {remaining} يوم × {daily} = {amount} ر.س (سجل المخصصات)'
            )
            return accrued, used, remaining, amount, text

    if not employee.hire_date:
        return Decimal('0'), used, Decimal('0'), Decimal('0'), 'لا يوجد تاريخ مباشرة — لم يُحسب رصيد الإجازة'

    months = completed_service_months(employee.hire_date, end)
    if flat_21_only:
        accrued = (Decimal(months) * MONTHLY_LEAVE_ACCRUAL_DAYS).quantize(LEAVE_DAYS_QUANT)
        rule = '21 يوم/سنة = 1.75 يوم/شهر'
    else:
        accrued = compute_monthly_tiered_leave_accrued_days(months)
        if months <= FIRST_FIVE_YEARS_MONTHS:
            rule = '21 يوم/سنة = 1.75 يوم/شهر (أول 5 سنوات)'
        else:
            rule = '105 يوم (5 سنوات) + 2.5 يوم/شهر × الأشهر الزائدة'

    remaining = (accrued - used).quantize(LEAVE_DAYS_QUANT)
    if remaining < 0:
        remaining = Decimal('0.00')

    daily = daily_rate_from_total(employee.total_salary)
    amount = (remaining * daily).quantize(Decimal('0.01'))
    prefix = f'{title} — ' if title else ''
    text = (
        f'{prefix}رصيد إجازات\n'
        f'قاعدة الاستحقاق: {rule}\n'
        f'أشهر الخدمة المكتملة: {months}\n'
        f'المستحق: {accrued} يوم − المستخدم: {used} = {remaining} يوم\n'
        f'رصيد الإجازة: {remaining} يوم × {daily} = {amount} ر.س'
    )
    return accrued, used, remaining, amount, text
