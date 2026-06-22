"""إعادة حساب سجل المخصصات (EmployeeLedger) على قاعدة الشهر = 30 يوماً."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.salary_month import (
    MONTHLY_LEAVE_ACCRUAL_DAYS,
    accrued_annual_leave_days,
    calendar_month_last_day,
    daily_rate_from_total,
    employment_service_days,
    salary_month_days,
    service_years_30day,
)
from apps.employees.models import Employee, EmployeeLedger

LEAVE_QUANT = Decimal('0.0001')
AMOUNT_QUANT = Decimal('0.01')


@dataclass
class LedgerRecalcResult:
    employee_id: int
    entries_updated: int
    entries_removed: int
    final_leave_days: Decimal
    final_leave_amount: Decimal
    skipped: bool = False
    reason: str = ''


def _quantize_leave(value) -> Decimal:
    return Decimal(value or 0).quantize(LEAVE_QUANT)


def _quantize_amount(value) -> Decimal:
    return Decimal(value or 0).quantize(AMOUNT_QUANT)


def _eosb_cumulative_amount(employee: Employee, as_of: date) -> Decimal:
    if not employee.sponsorship_id or not employee.hire_date:
        return Decimal('0.00')
    service_days = employment_service_days(employee.hire_date, as_of)
    if service_days < 1:
        return Decimal('0.00')
    service_years = service_years_30day(service_days)
    eosb_base = Decimal(employee.salary_for_end_of_service or 0)
    half = (eosb_base / Decimal('2')).quantize(AMOUNT_QUANT)
    if service_years <= 5:
        return (half * service_years).quantize(AMOUNT_QUANT)
    first_5 = (half * Decimal('5')).quantize(AMOUNT_QUANT)
    extra_years = service_years - Decimal('5')
    extra = (eosb_base * extra_years).quantize(AMOUNT_QUANT)
    return (first_5 + extra).quantize(AMOUNT_QUANT)


def _eosb_detail_text(employee: Employee, as_of: date) -> str:
    if not employee.sponsorship_id or not employee.hire_date:
        return 'لا يوجد كفالة — لم يُحسب استحقاق نهاية الخدمة'
    service_days = employment_service_days(employee.hire_date, as_of)
    service_years = service_years_30day(service_days)
    eosb_base = Decimal(employee.salary_for_end_of_service or 0)
    half = (eosb_base / Decimal('2')).quantize(AMOUNT_QUANT)
    if service_years <= 5:
        amt = (half * service_years).quantize(AMOUNT_QUANT)
        return f'≤5 سنوات: {half} × {service_years} = {amt} ر.س'
    first_5 = (half * Decimal('5')).quantize(AMOUNT_QUANT)
    extra_years = service_years - Decimal('5')
    extra = (eosb_base * extra_years).quantize(AMOUNT_QUANT)
    total = (first_5 + extra).quantize(AMOUNT_QUANT)
    return (
        f'أول 5 سنوات: {half} × 5 = {first_5} | '
        f'بعد 5 سنوات: {eosb_base} × {extra_years} = {extra} | الإجمالي = {total}'
    )


def _compute_monthly_changes(employee: Employee, entry: EmployeeLedger) -> tuple[Decimal, Decimal, Decimal, str]:
    from apps.employees.services.accrual_ledger_notes import (
        build_monthly_payroll_notes,
        compute_monthly_ledger_amounts,
    )
    from apps.payroll.models import PayrollLine

    run = entry.payroll_run
    if not run:
        days = _quantize_leave(entry.leave_days_change)
        daily = daily_rate_from_total(employee.total_salary)
        amount = _quantize_amount(days * daily)
        return days, amount, _quantize_amount(entry.eosb_amount_change), entry.notes or ''

    line = (
        PayrollLine.objects.filter(run_id=run.id, employee_id=employee.pk)
        .only('gross_salary', 'meal_allowance')
        .first()
    )
    gross = Decimal(line.gross_salary or 0) if line else Decimal(employee.total_salary or 0)
    eosb_base = gross - Decimal(line.meal_allowance or 0) if line else Decimal(employee.salary_for_end_of_service or 0)

    leave_days_change = MONTHLY_LEAVE_ACCRUAL_DAYS
    calc = compute_monthly_ledger_amounts(
        gross_salary=gross,
        eosb_base=eosb_base,
        hire_date=employee.hire_date,
        period_year=run.period_year,
        period_month=run.period_month,
        eligible_for_eosb=bool(employee.sponsorship_id),
    )
    leave_amount_change = calc['leave_amount']
    eosb_amount_change = calc['eosb']
    return leave_days_change, leave_amount_change, eosb_amount_change, ''


def _compute_initial_changes(
    employee: Employee,
    entry: EmployeeLedger,
    prev_leave_days: Decimal,
    prev_leave_amt: Decimal,
    prev_eosb: Decimal,
) -> tuple[Decimal, Decimal, Decimal, str]:
    from apps.employees.services.accrual_ledger_notes import build_initial_balance_notes

    if not employee.hire_date:
        return Decimal('0'), Decimal('0'), Decimal('0'), entry.notes or ''

    target_days = accrued_annual_leave_days(employee.hire_date, entry.date)
    leave_days_change = _quantize_leave(target_days - prev_leave_days)
    daily = daily_rate_from_total(employee.total_salary)
    leave_amount_change = _quantize_amount(leave_days_change * daily)

    target_eosb = _eosb_cumulative_amount(employee, entry.date)
    eosb_amount_change = _quantize_amount(target_eosb - prev_eosb)
    eosb_detail = _eosb_detail_text(employee, entry.date)

    notes = build_initial_balance_notes(
        hire_date=employee.hire_date,
        as_of_date=entry.date,
        total_salary=Decimal(employee.total_salary or 0),
        leave_days=target_days,
        leave_amount=_quantize_amount(target_days * daily),
        eosb=target_eosb,
        eosb_detail=eosb_detail,
    )
    return leave_days_change, leave_amount_change, eosb_amount_change, notes


def _compute_entry_changes(
    employee: Employee,
    entry: EmployeeLedger,
    prev_leave_days: Decimal,
    prev_leave_amt: Decimal,
    prev_eosb: Decimal,
) -> tuple[Decimal, Decimal, Decimal, str]:
    tx = entry.transaction_type
    daily = daily_rate_from_total(employee.total_salary)

    if tx == EmployeeLedger.TransactionType.INITIAL_BALANCE:
        return _compute_initial_changes(employee, entry, prev_leave_days, prev_leave_amt, prev_eosb)

    if tx == EmployeeLedger.TransactionType.MONTHLY_PAYROLL:
        days, amount, eosb, _ = _compute_monthly_changes(employee, entry)
        notes = ''
        if entry.payroll_run_id:
            from apps.employees.services.accrual_ledger_notes import build_monthly_payroll_notes
            from apps.payroll.models import PayrollLine

            run = entry.payroll_run
            line = PayrollLine.objects.filter(run_id=run.id, employee_id=employee.pk).first()
            gross = Decimal(line.gross_salary or 0) if line else Decimal(employee.total_salary or 0)
            notes = build_monthly_payroll_notes(
                period_year=run.period_year,
                period_month=run.period_month,
                month_days=salary_month_days(run.period_year, run.period_month),
                gross_salary=gross,
                daily_rate=daily_rate_from_total(gross),
                hire_date=employee.hire_date,
                prev_leave_days=prev_leave_days,
                prev_leave_amount=prev_leave_amt,
                prev_eosb=prev_eosb,
                leave_days_change=days,
                leave_amount_change=amount,
                eosb_amount_change=eosb,
                cumulative_leave_days=_quantize_leave(prev_leave_days + days),
                cumulative_leave_amount=_quantize_amount(prev_leave_amt + amount),
                cumulative_eosb=_quantize_amount(prev_eosb + eosb),
                payroll_run_id=run.id,
            )
        return days, amount, eosb, notes

    if tx == EmployeeLedger.TransactionType.LEAVE_TAKEN:
        days = _quantize_leave(abs(entry.leave_days_change))
        leave_days_change = -days
        leave_amount_change = _quantize_amount(-(days * daily))
        return leave_days_change, leave_amount_change, Decimal('0.00'), entry.notes or ''

    if tx == EmployeeLedger.TransactionType.FINAL_SETTLEMENT:
        return (
            _quantize_leave(-prev_leave_days),
            _quantize_amount(-prev_leave_amt),
            _quantize_amount(-prev_eosb),
            entry.notes or 'تصفية نهائية وتصفير الرصيد',
        )

    if tx == EmployeeLedger.TransactionType.MANUAL_ADJUSTMENT:
        days = _quantize_leave(entry.leave_days_change)
        return days, _quantize_amount(days * daily), _quantize_amount(entry.eosb_amount_change), entry.notes or ''

    days = _quantize_leave(entry.leave_days_change)
    return days, _quantize_amount(entry.leave_amount_change), _quantize_amount(entry.eosb_amount_change), entry.notes or ''


@transaction.atomic
def recalculate_employee_ledger(
    employee: Employee | int,
    *,
    dry_run: bool = False,
) -> LedgerRecalcResult:
    """إعادة حساب قيود المخصصات لموظف واحد."""
    if isinstance(employee, int):
        employee = Employee.objects.get(pk=employee)

    entries = list(
        EmployeeLedger.all_objects.filter(employee_id=employee.pk)
        .select_related('payroll_run')
        .order_by('date', 'created_at', 'id'),
    )
    active = [e for e in entries if not e.is_deleted]
    has_monthly = any(e.transaction_type == EmployeeLedger.TransactionType.MONTHLY_PAYROLL for e in active)

    to_remove = [
        e for e in active
        if e.transaction_type == EmployeeLedger.TransactionType.INITIAL_BALANCE and has_monthly
    ]
    to_process = [e for e in active if e not in to_remove]

    prev_days = prev_amt = prev_eosb = Decimal('0')
    updated = 0

    for entry in to_process:
        days_ch, amt_ch, eosb_ch, notes = _compute_entry_changes(
            employee, entry, prev_days, prev_amt, prev_eosb,
        )
        cum_days = _quantize_leave(prev_days + days_ch)
        cum_amt = _quantize_amount(prev_amt + amt_ch)
        cum_eosb = _quantize_amount(prev_eosb + eosb_ch)

        if not dry_run:
            entry.leave_days_change = days_ch
            entry.leave_amount_change = amt_ch
            entry.eosb_amount_change = eosb_ch
            entry.cumulative_leave_days = cum_days
            entry.cumulative_leave_amount = cum_amt
            entry.cumulative_eosb_amount = cum_eosb
            if notes:
                entry.notes = notes
            entry.save(
                update_fields=[
                    'leave_days_change',
                    'leave_amount_change',
                    'eosb_amount_change',
                    'cumulative_leave_days',
                    'cumulative_leave_amount',
                    'cumulative_eosb_amount',
                    'notes',
                    'updated_at',
                ],
            )

        prev_days, prev_amt, prev_eosb = cum_days, cum_amt, cum_eosb
        updated += 1

    if not dry_run:
        now = timezone.now()
        for entry in to_remove:
            entry.is_deleted = True
            entry.deleted_at = now
            entry.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    return LedgerRecalcResult(
        employee_id=employee.pk,
        entries_updated=updated,
        entries_removed=len(to_remove),
        final_leave_days=prev_days,
        final_leave_amount=prev_amt,
    )


def recalculate_all_employee_ledgers(
    *,
    employee_ids: list[int] | None = None,
    dry_run: bool = False,
) -> list[LedgerRecalcResult]:
    """إعادة حساب المخصصات لكل الموظفين الذين لديهم سجل."""
    qs = Employee.objects.filter(accruals_ledger__isnull=False).distinct()
    if employee_ids:
        qs = qs.filter(pk__in=employee_ids)

    results: list[LedgerRecalcResult] = []
    for emp in qs.iterator():
        results.append(recalculate_employee_ledger(emp, dry_run=dry_run))
    return results
