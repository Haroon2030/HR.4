"""مستحقات وخصومات التصفية — راتب الفترة، سلف، غيابات غير مُحتسبة."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.core.salary_month import STANDARD_MONTH_DAYS
from apps.employees.models import (
    Employee,
    EmployeeAbsence,
    EmployeeCashShortage,
    EmployeeLoan,
    EmployeeStatement,
)


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


def pending_penalties_deduction(employee: Employee, *, as_of: date) -> Decimal:
    """مخالفات (جزاءات مالية) لم تُحتسب في مسير بعد — حتى تاريخ التوقف."""
    qs = EmployeeStatement.objects.filter(
        employee=employee,
        statement_type=EmployeeStatement.StatementType.PENALTY,
        applied_to_payroll__isnull=True,
        statement_date__lte=as_of,
    )
    return _quantize(sum((Decimal(str(p.deduction_amount or 0)) for p in qs), Decimal('0')))


def pending_cash_shortages_deduction(employee: Employee, *, as_of: date) -> Decimal:
    """عجز كاشير لم يُحتسب في مسير بعد — حتى تاريخ التوقف."""
    qs = EmployeeCashShortage.objects.filter(
        employee=employee,
        applied_to_payroll__isnull=True,
        shortage_date__lte=as_of,
    )
    return _quantize(sum((Decimal(str(c.amount or 0)) for c in qs), Decimal('0')))


def salary_paid_in_locked_payroll(employee: Employee, end_date: date) -> tuple[Decimal, Decimal]:
    """
    ما صُرف فعلاً في مسيرات مُرحَّلة:
    - (المصروف عن شهر التوقف، المصروف عن أشهر بعد شهر التوقف)
    الأشهر اللاحقة لتاريخ التوقف كلها زيادة يجب استردادها.
    """
    from django.db.models import Q, Sum

    from apps.payroll.models import PayrollLine, PayrollRun
    from apps.payroll.services.engine import PAYING_RUN_KINDS

    locked = PayrollLine.objects.filter(
        employee=employee,
        run__status=PayrollRun.Status.LOCKED,
        run__run_kind__in=PAYING_RUN_KINDS,
    )
    same_month = locked.filter(
        run__period_year=end_date.year, run__period_month=end_date.month,
    ).aggregate(s=Sum('gross_salary'))['s'] or Decimal('0')
    later = locked.filter(
        Q(run__period_year__gt=end_date.year)
        | Q(run__period_year=end_date.year, run__period_month__gt=end_date.month),
    ).aggregate(s=Sum('gross_salary'))['s'] or Decimal('0')
    return _quantize(Decimal(same_month)), _quantize(Decimal(later))


def compute_settlement_financials(employee: Employee, end_date: date) -> dict:
    """
    يُرجع بنود التسوية المالية عند التصفية:
    - prorated_salary: راتب الفترة المتبقي للصرف (بعد طرح ما صُرف في مسير مُرحَّل لنفس الشهر)
    - overpaid_salary_recovery: ما صُرف زيادةً عن الاستحقاق (مسير مُرحَّل كامل ثم توقف مبكر) — يُسترد
    - loans / absences / penalties / cash shortages: خصومات معلّقة لم تُحتسب في مسير
    """
    entitled = prorated_salary_until(employee, end_date)
    paid_same_month, paid_later_months = salary_paid_in_locked_payroll(employee, end_date)
    prorated = _quantize(max(entitled - paid_same_month, Decimal('0')))
    overpaid = _quantize(max(paid_same_month - entitled, Decimal('0')) + paid_later_months)

    loans = pending_loans_deduction(employee)
    absences = pending_absences_deduction(employee, as_of=end_date)
    penalties = pending_penalties_deduction(employee, as_of=end_date)
    shortages = pending_cash_shortages_deduction(employee, as_of=end_date)
    deductions = _quantize(loans + absences + penalties + shortages + overpaid)
    return {
        'prorated_salary': prorated,
        'entitled_salary': entitled,
        'salary_already_paid': paid_same_month,
        'overpaid_salary_recovery': overpaid,
        'loans_deduction': loans,
        'absences_deduction': absences,
        'penalties_deduction': penalties,
        'cash_shortages_deduction': shortages,
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
