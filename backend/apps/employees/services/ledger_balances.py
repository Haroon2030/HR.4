"""أرصدة المخصصات من EmployeeLedger — المصدر الموحّد للتصفية."""
from __future__ import annotations

from decimal import Decimal


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
    مستحقات الإجازة عند التصفية — يفوّض إلى leave_balance الموحّد.
    Returns: (leave_days, leave_amount, descriptive_text)
    """
    from apps.employees.services.leave_balance import settlement_leave_for_employee

    _, _, remaining, amount, text = settlement_leave_for_employee(employee)
    return remaining, amount, text
