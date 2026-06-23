"""مستحقات وخصومات التصفية — راتب الفترة، سلف، غيابات غير مُحتسبة."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.core.salary_month import STANDARD_MONTH_DAYS
from apps.employees.models import Employee, EmployeeAbsence, EmployeeLoan


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal('0.01'))


def prorated_salary_until(employee: Employee, end_date: date) -> Decimal:
    """راتب الشهر الأخير حتى تاريخ التوقف (نفس قاعدة مسير الرواتب)."""
    from apps.payroll.services.period_eligibility import employee_payroll_period, prorate_amount

    gross = Decimal(employee.total_salary or 0)
    if gross <= 0:
        return Decimal('0.00')

    period = employee_payroll_period(
        period_year=end_date.year,
        period_month=end_date.month,
        hire_date=getattr(employee, 'hire_date', None),
        end_date=end_date,
    )
    return prorate_amount(gross, period['payable_base_days'], period['month_days'])


def pending_loans_deduction(employee: Employee) -> Decimal:
    """مجموع أرصدة السلف النشطة غير المسددة."""
    total = Decimal('0')
    for loan in employee.loans.filter(status=EmployeeLoan.Status.ACTIVE):
        balance = loan.remaining_balance
        if balance and balance > 0:
            total += Decimal(str(balance))
    return _quantize(total)


def pending_absences_deduction(employee: Employee, *, as_of: date) -> Decimal:
    """غيابات لم تُحتسب في مسير بعد — حتى تاريخ التوقف."""
    qs = EmployeeAbsence.objects.filter(
        employee=employee,
        applied_to_payroll__isnull=True,
        absence_date__lte=as_of,
    )
    total = sum((Decimal(str(a.deduction_amount or 0)) for a in qs), Decimal('0'))
    return _quantize(total)


def compute_settlement_financials(employee: Employee, end_date: date) -> dict:
    """
    يُرجع بنود التسوية المالية عند التصفية:
    - prorated_salary: مستحق راتب الفترة
    - loans_deduction / absences_deduction: خصومات
    - total_deductions / net_payable: بعد خصم السلف والغياب
    """
    prorated = prorated_salary_until(employee, end_date)
    loans = pending_loans_deduction(employee)
    absences = pending_absences_deduction(employee, as_of=end_date)
    deductions = _quantize(loans + absences)
    return {
        'prorated_salary': prorated,
        'loans_deduction': loans,
        'absences_deduction': absences,
        'total_deductions': deductions,
        'month_days': STANDARD_MONTH_DAYS,
    }


def net_settlement_total(
    *,
    eosb: Decimal,
    leave_comp: Decimal,
    penalty: Decimal,
    financials: dict,
) -> Decimal:
    """صافي المستحق = مكافأة + إجازة + جزاء + راتب الفترة − سلف − غياب."""
    gross = _quantize(
        Decimal(eosb or 0)
        + Decimal(leave_comp or 0)
        + Decimal(penalty or 0)
        + Decimal(financials.get('prorated_salary') or 0)
    )
    return _quantize(gross - Decimal(financials.get('total_deductions') or 0))
