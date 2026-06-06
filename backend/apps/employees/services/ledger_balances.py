"""أرصدة المخصصات من EmployeeLedger — المصدر الموحّد للتصفية."""
from __future__ import annotations

from decimal import Decimal

from apps.core.salary_month import daily_rate_from_total


def get_latest_ledger_balance(employee):
    """آخر قيد تراكمي للموظف أو None."""
    from apps.employees.models import EmployeeLedger

    return (
        EmployeeLedger.objects.filter(employee=employee)
        .order_by('-date', '-created_at')
        .first()
    )


def settlement_leave_from_ledger(employee) -> tuple[Decimal, Decimal, str]:
    """
    مستحقات الإجازة عند التصفية من الدفتر.
    Returns: (leave_days, leave_amount, descriptive_text)
    """
    if not employee.sponsorship_id:
        return Decimal('0'), Decimal('0'), 'لا يوجد كفالة — لم تُحتسب مستحقات الإجازة'

    last = get_latest_ledger_balance(employee)
    if not last:
        return Decimal('0'), Decimal('0'), 'لا يوجد رصيد إجازة في سجل المخصصات'

    leave_days = Decimal(last.cumulative_leave_days or 0)
    leave_amount = Decimal(last.cumulative_leave_amount or 0)

    if leave_amount <= 0 and leave_days > 0:
        daily = daily_rate_from_total(employee.total_salary)
        leave_amount = (leave_days * daily).quantize(Decimal('0.01'))

    if leave_days <= 0:
        return Decimal('0'), Decimal('0'), 'رصيد الإجازة في الدفتر: 0 يوم'

    daily = daily_rate_from_total(employee.total_salary)
    text = (
        f'رصيد الدفتر: {leave_days} يوم × {daily} = {leave_amount} ر.س '
        f'(سجل المخصصات)'
    )
    return leave_days, leave_amount, text
