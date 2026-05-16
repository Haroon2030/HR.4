"""نصوص تفاصيل العمليات الحسابية لسجل المخصصات (EmployeeLedger)."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

# 21 يوم إجازة سنوياً ÷ 12 شهر
MONTHLY_LEAVE_ACCRUAL_DAYS = Decimal('1.75')


def monthly_eosb_accrual(gross: Decimal, service_years: float) -> tuple[Decimal, str]:
    """استحقاق شهري لمكافأة نهاية الخدمة (نظام العمل السعودي)."""
    gross = Decimal(gross or 0)
    if service_years <= 5:
        amt = (gross / Decimal('24')).quantize(Decimal('0.01'))
        detail = f'≤5 سنوات خدمة: {gross} ÷ 24 = {amt} ر.س/شهر'
    else:
        amt = (gross / Decimal('12')).quantize(Decimal('0.01'))
        detail = f'>5 سنوات خدمة: {gross} ÷ 12 = {amt} ر.س/شهر'
    return amt, detail


def compute_monthly_ledger_amounts(
    *,
    gross_salary: Decimal,
    daily_rate: Decimal,
    hire_date: date | None,
    period_year: int,
    period_month: int,
) -> dict:
    """حساب مبالغ مخصص الشهر (نفس منطق lock_payroll_run)."""
    gross = Decimal(gross_salary or 0)
    daily = Decimal(daily_rate or 0) or (gross / Decimal('30')).quantize(Decimal('0.01'))
    leave_days = MONTHLY_LEAVE_ACCRUAL_DAYS
    leave_amount = (leave_days * daily).quantize(Decimal('0.01'))

    eosb = Decimal('0')
    eosb_detail = 'لا يوجد تاريخ مباشرة — لم يُحسب استحقاق نهاية الخدمة'
    service_days = 0
    service_years = 0.0

    if hire_date:
        last_day = monthrange(period_year, period_month)[1]
        month_end = date(period_year, period_month, last_day)
        service_days = (month_end - hire_date).days
        service_years = service_days / 365.25
        eosb, eosb_detail = monthly_eosb_accrual(gross, service_years)

    return {
        'leave_days': leave_days,
        'leave_amount': leave_amount,
        'eosb': eosb,
        'eosb_detail': eosb_detail,
        'daily_rate': daily,
        'gross': gross,
        'service_days': service_days,
        'service_years': round(service_years, 4),
        'month_end': date(period_year, period_month, monthrange(period_year, period_month)[1]),
    }


def build_initial_balance_notes(
    *,
    hire_date: date,
    as_of_date: date,
    total_salary: Decimal,
    leave_days: Decimal,
    leave_amount: Decimal,
    eosb: Decimal,
    eosb_detail: str,
) -> str:
    service_days = (as_of_date - hire_date).days
    service_years = Decimal(str(round(service_days / 365.25, 4)))
    daily_wage = (total_salary / Decimal('30')).quantize(Decimal('0.01'))
    return (
        f'عملية: رصيد افتتاحي (من المباشرة حتى {as_of_date})\n'
        f'تاريخ المباشرة: {hire_date} | مدة الخدمة: {service_days} يوم ({service_years} سنة)\n'
        f'── الإجازات ──\n'
        f'الراتب الإجمالي: {total_salary} ر.س | أجر اليوم: {total_salary} ÷ 30 = {daily_wage} ر.س\n'
        f'أيام مستحقة: {service_days} × 21 ÷ 365.25 = {leave_days} يوم\n'
        f'قيمة الإجازات: {leave_days} × {daily_wage} = {leave_amount} ر.س\n'
        f'── مكافأة نهاية الخدمة (تراكمي حتى التاريخ) ──\n'
        f'{eosb_detail}\n'
        f'إجمالي الاستحقاق التراكمي: {eosb} ر.س'
    )


def build_monthly_payroll_notes(
    *,
    period_year: int,
    period_month: int,
    month_days: int,
    gross_salary: Decimal,
    daily_rate: Decimal,
    hire_date: date | None,
    prev_leave_days: Decimal,
    prev_leave_amount: Decimal,
    prev_eosb: Decimal,
    leave_days_change: Decimal,
    leave_amount_change: Decimal,
    eosb_amount_change: Decimal,
    cumulative_leave_days: Decimal,
    cumulative_leave_amount: Decimal,
    cumulative_eosb: Decimal,
    payroll_run_id: int | None = None,
) -> str:
    calc = compute_monthly_ledger_amounts(
        gross_salary=gross_salary,
        daily_rate=daily_rate,
        hire_date=hire_date,
        period_year=period_year,
        period_month=period_month,
    )
    run_ref = f' | مسير #{payroll_run_id}' if payroll_run_id else ''
    return (
        f'عملية: مخصص شهري — إقفال مسير رواتب {period_month}/{period_year}{run_ref}\n'
        f'تاريخ القيد: آخر يوم في الشهر ({calc["month_end"]}) | أيام الشهر: {month_days}\n'
        f'── استحقاق الإجازة السنوية (21 يوم/سنة) ──\n'
        f'المعدل الشهري: 21 ÷ 12 = {MONTHLY_LEAVE_ACCRUAL_DAYS} يوم\n'
        f'الراتب الإجمالي (لقطة المسير): {calc["gross"]} ر.س\n'
        f'أجر اليوم: {calc["gross"]} ÷ {month_days} = {calc["daily_rate"]} ر.س\n'
        f'قيمة المخصص: {leave_days_change} × {calc["daily_rate"]} = {leave_amount_change} ر.س\n'
        f'رصيد أيام الإجازة: {prev_leave_days} + {leave_days_change} = {cumulative_leave_days} يوم\n'
        f'رصيد قيمة الإجازات: {prev_leave_amount} + {leave_amount_change} = {cumulative_leave_amount} ر.س\n'
        f'── استحقاق مكافأة نهاية الخدمة (شهري) ──\n'
        f'مدة الخدمة عند {calc["month_end"]}: {calc["service_days"]} يوم ({calc["service_years"]} سنة)\n'
        f'{calc["eosb_detail"]}\n'
        f'مخصص هذا الشهر: {eosb_amount_change} ر.س\n'
        f'رصيد المكافأة: {prev_eosb} + {eosb_amount_change} = {cumulative_eosb} ر.س'
    )


def display_ledger_notes(ledger) -> str:
    """نص العرض في الواجهة — يُثرى تلقائياً للسجلات القديمة ذات الملاحظات القصيرة."""
    raw = (ledger.notes or '').strip()
    if raw and '\n' in raw and len(raw) > 60:
        return raw

    from apps.employees.models import EmployeeLedger

    if ledger.transaction_type == EmployeeLedger.TransactionType.MONTHLY_PAYROLL and ledger.payroll_run_id:
        from apps.payroll.models import PayrollLine

        line = (
            PayrollLine.objects.filter(
                run_id=ledger.payroll_run_id,
                employee_id=ledger.employee_id,
            )
            .only('gross_salary', 'daily_rate', 'month_days')
            .first()
        )
        if line:
            run = ledger.payroll_run
            prev = (
                EmployeeLedger.objects.filter(
                    employee_id=ledger.employee_id,
                    date__lt=date(run.period_year, run.period_month, 1),
                )
                .order_by('-date', '-created_at')
                .first()
            )
            hire = ledger.employee.hire_date

            return build_monthly_payroll_notes(
                period_year=run.period_year,
                period_month=run.period_month,
                month_days=line.month_days or monthrange(run.period_year, run.period_month)[1],
                gross_salary=line.gross_salary,
                daily_rate=line.daily_rate,
                hire_date=hire,
                prev_leave_days=prev.cumulative_leave_days if prev else Decimal('0'),
                prev_leave_amount=prev.cumulative_leave_amount if prev else Decimal('0'),
                prev_eosb=prev.cumulative_eosb_amount if prev else Decimal('0'),
                leave_days_change=ledger.leave_days_change,
                leave_amount_change=ledger.leave_amount_change,
                eosb_amount_change=ledger.eosb_amount_change,
                cumulative_leave_days=ledger.cumulative_leave_days,
                cumulative_leave_amount=ledger.cumulative_leave_amount,
                cumulative_eosb=ledger.cumulative_eosb_amount,
                payroll_run_id=ledger.payroll_run_id,
            )

    if ledger.transaction_type == EmployeeLedger.TransactionType.INITIAL_BALANCE and raw:
        return raw

    return raw or 'لا توجد تفاصيل محفوظة لهذه العملية.'
