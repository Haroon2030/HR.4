"""نصوص تفاصيل العمليات الحسابية لسجل المخصصات (EmployeeLedger)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.core.salary_month import (
    STANDARD_MONTH_DAYS,
    calendar_month_last_day,
    daily_rate_from_total,
    salary_month_days,
)

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
    daily_rate: Decimal | None = None,
    eosb_base: Decimal | None = None,
    hire_date: date | None,
    period_year: int,
    period_month: int,
) -> dict:
    """حساب مبالغ مخصص الشهر — أجر اليوم = الإجمالي ÷ 30؛ EOSB بدون بدل التغذية."""
    gross = Decimal(gross_salary or 0)
    eosb_gross = Decimal(eosb_base if eosb_base is not None else gross_salary or 0)
    daily = daily_rate_from_total(gross)
    leave_days = MONTHLY_LEAVE_ACCRUAL_DAYS
    leave_amount = (leave_days * daily).quantize(Decimal('0.01'))

    eosb = Decimal('0')
    eosb_detail = 'لا يوجد تاريخ مباشرة — لم يُحسب استحقاق نهاية الخدمة'
    service_days = 0
    service_years = 0.0

    if hire_date:
        month_end = calendar_month_last_day(period_year, period_month)
        service_days = (month_end - hire_date).days
        service_years = service_days / 365.25
        eosb, eosb_detail = monthly_eosb_accrual(eosb_gross, service_years)

    return {
        'leave_days': leave_days,
        'leave_amount': leave_amount,
        'eosb': eosb,
        'eosb_detail': eosb_detail,
        'daily_rate': daily,
        'gross': gross,
        'eosb_base': eosb_gross,
        'service_days': service_days,
        'service_years': round(service_years, 4),
        'month_end': calendar_month_last_day(period_year, period_month),
        'month_days': STANDARD_MONTH_DAYS,
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
    daily_wage = daily_rate_from_total(total_salary)
    return (
        f'عملية: رصيد افتتاحي (من المباشرة حتى {as_of_date})\n'
        f'تاريخ المباشرة: {hire_date} | مدة الخدمة: {service_days} يوم ({service_years} سنة)\n'
        f'── الإجازات ──\n'
        f'الراتب الإجمالي: {total_salary} ر.س | أجر اليوم: {total_salary} ÷ {STANDARD_MONTH_DAYS} = {daily_wage} ر.س\n'
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
        hire_date=hire_date,
        period_year=period_year,
        period_month=period_month,
    )
    month_days = STANDARD_MONTH_DAYS
    run_ref = f' | مسير #{payroll_run_id}' if payroll_run_id else ''
    return (
        f'عملية: مخصص شهري — إقفال مسير رواتب {period_month}/{period_year}{run_ref}\n'
        f'تاريخ القيد: آخر يوم في الشهر ({calc["month_end"]}) | أيام الشهر (للحساب): {month_days}\n'
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


def _q(value: Decimal | float | int, places: int = 2) -> str:
    return f'{Decimal(value):.{places}f}'


def get_ledger_display_context(ledger) -> dict:
    """هيكل منظم لعرض تفاصيل العملية في الواجهة."""
    from apps.employees.models import EmployeeLedger

    tx = ledger.transaction_type

    if tx == EmployeeLedger.TransactionType.MONTHLY_PAYROLL:
        ctx = _monthly_display_context(ledger)
        if ctx:
            return ctx

    if tx == EmployeeLedger.TransactionType.INITIAL_BALANCE:
        ctx = _initial_display_context(ledger)
        if ctx:
            return ctx

    return {
        'kind': 'plain',
        'text': display_ledger_notes(ledger),
    }


def _monthly_display_context(ledger) -> dict | None:
    from apps.employees.models import EmployeeLedger
    from apps.payroll.models import PayrollLine

    if not ledger.payroll_run_id:
        return None

    line = (
        PayrollLine.objects.filter(
            run_id=ledger.payroll_run_id,
            employee_id=ledger.employee_id,
        )
        .only('gross_salary', 'daily_rate', 'month_days')
        .first()
    )
    if not line:
        return None

    run = ledger.payroll_run
    month_days = STANDARD_MONTH_DAYS
    prev = (
        EmployeeLedger.objects.filter(
            employee_id=ledger.employee_id,
            date__lt=date(run.period_year, run.period_month, 1),
        )
        .order_by('-date', '-created_at')
        .first()
    )
    prev_leave_days = prev.cumulative_leave_days if prev else Decimal('0')
    prev_leave_amt = prev.cumulative_leave_amount if prev else Decimal('0')
    prev_eosb = prev.cumulative_eosb_amount if prev else Decimal('0')

    calc = compute_monthly_ledger_amounts(
        gross_salary=line.gross_salary,
        hire_date=ledger.employee.hire_date,
        period_year=run.period_year,
        period_month=run.period_month,
    )
    display_daily = calc['daily_rate']
    display_leave_amount = (
        Decimal(ledger.leave_days_change or 0) * display_daily
    ).quantize(Decimal('0.01'))
    eosb_rule = '≤5 سنوات خدمة' if calc['service_years'] <= 5 else '>5 سنوات خدمة'
    eosb_divisor = '24' if calc['service_years'] <= 5 else '12'

    return {
        'kind': 'structured',
        'operation': 'مخصص شهري — إقفال مسير رواتب',
        'period': f'{run.period_month}/{run.period_year}',
        'meta': [
            {'label': 'مسير الرواتب', 'value': f'#{ledger.payroll_run_id}', 'mono': True},
            {'label': 'تاريخ القيد', 'value': calc['month_end'].strftime('%Y-%m-%d'), 'mono': True},
            {'label': 'أيام الشهر', 'value': str(month_days), 'mono': True},
        ],
        'sections': [
            {
                'id': 'leave',
                'title': 'استحقاق الإجازة السنوية',
                'hint': '21 يوم في السنة',
                'theme': 'emerald',
                'rows': [
                    {'label': 'المعدل الشهري', 'formula': '21 ÷ 12', 'result': f'{_q(MONTHLY_LEAVE_ACCRUAL_DAYS)} يوم'},
                    {'label': 'الراتب الإجمالي (لقطة المسير)', 'formula': None, 'result': f'{_q(calc["gross"])} ر.س'},
                    {'label': 'أجر اليوم', 'formula': f'{_q(calc["gross"])} ÷ {month_days}', 'result': f'{_q(calc["daily_rate"])} ر.س'},
                    {
                        'label': 'قيمة مخصص هذا الشهر',
                        'formula': f'{_q(ledger.leave_days_change, 4)} × {_q(display_daily)}',
                        'result': f'{_q(display_leave_amount)} ر.س',
                        'highlight': True,
                    },
                ],
                'balance': {
                    'label': 'رصيد أيام الإجازة',
                    'before': _q(prev_leave_days, 4),
                    'change': f'+{_q(ledger.leave_days_change, 4)}',
                    'after': _q(ledger.cumulative_leave_days, 4),
                    'unit': 'يوم',
                },
                'balance_money': {
                    'label': 'رصيد قيمة الإجازات',
                    'before': _q(prev_leave_amt),
                    'change': f'+{_q(ledger.leave_amount_change)}',
                    'after': _q(ledger.cumulative_leave_amount),
                    'unit': 'ر.س',
                },
            },
            {
                'id': 'eosb',
                'title': 'مكافأة نهاية الخدمة',
                'hint': 'استحقاق شهري',
                'theme': 'amber',
                'rows': [
                    {
                        'label': 'مدة الخدمة عند نهاية الشهر',
                        'formula': None,
                        'result': f'{calc["service_days"]} يوم ({calc["service_years"]} سنة)',
                    },
                    {
                        'label': eosb_rule,
                        'formula': f'{_q(calc["gross"])} ÷ {eosb_divisor}',
                        'result': f'{_q(ledger.eosb_amount_change)} ر.س/شهر',
                    },
                    {
                        'label': 'مخصص هذا الشهر',
                        'formula': None,
                        'result': f'{_q(ledger.eosb_amount_change)} ر.س',
                        'highlight': True,
                    },
                ],
                'balance': {
                    'label': 'رصيد المكافأة التراكمي',
                    'before': _q(prev_eosb),
                    'change': f'+{_q(ledger.eosb_amount_change)}',
                    'after': _q(ledger.cumulative_eosb_amount),
                    'unit': 'ر.س',
                },
            },
        ],
    }


def _initial_display_context(ledger) -> dict | None:
    from apps.employees.models import EmployeeLedger

    if ledger.transaction_type != EmployeeLedger.TransactionType.INITIAL_BALANCE:
        return None

    emp = ledger.employee
    if not emp.hire_date:
        return None

    as_of = ledger.date
    service_days = (as_of - emp.hire_date).days
    service_years = round(service_days / 365.25, 4)
    total_salary = Decimal(emp.total_salary or 0)
    daily_wage = daily_rate_from_total(total_salary)

    return {
        'kind': 'structured',
        'operation': 'رصيد افتتاحي',
        'period': f'حتى {as_of.strftime("%Y-%m-%d")}',
        'meta': [
            {'label': 'تاريخ المباشرة', 'value': emp.hire_date.strftime('%Y-%m-%d'), 'mono': True},
            {'label': 'مدة الخدمة', 'value': f'{service_days} يوم ({service_years} سنة)', 'mono': True},
        ],
        'sections': [
            {
                'id': 'leave',
                'title': 'رصيد الإجازات المستحق',
                'hint': 'من تاريخ المباشرة',
                'theme': 'emerald',
                'rows': [
                    {'label': 'الراتب الإجمالي', 'formula': None, 'result': f'{_q(total_salary)} ر.س'},
                    {'label': 'أجر اليوم', 'formula': f'{_q(total_salary)} ÷ {STANDARD_MONTH_DAYS}', 'result': f'{_q(daily_wage)} ر.س'},
                    {
                        'label': 'أيام مستحقة',
                        'formula': f'{service_days} × 21 ÷ 365.25',
                        'result': f'{_q(ledger.leave_days_change)} يوم',
                        'highlight': True,
                    },
                    {
                        'label': 'قيمة الإجازات',
                        'formula': f'{_q(ledger.leave_days_change)} × {_q(daily_wage)}',
                        'result': f'{_q(ledger.leave_amount_change)} ر.س',
                        'highlight': True,
                    },
                ],
            },
            {
                'id': 'eosb',
                'title': 'مكافأة نهاية الخدمة',
                'hint': 'تراكمي حتى تاريخ الرصيد',
                'theme': 'amber',
                'rows': [
                    {
                        'label': 'إجمالي الاستحقاق التراكمي',
                        'formula': (ledger.notes or '').split('\n')[-1][:80] if ledger.notes else None,
                        'result': f'{_q(ledger.eosb_amount_change)} ر.س',
                        'highlight': True,
                    },
                ],
            },
        ],
    }


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
                month_days=STANDARD_MONTH_DAYS,
                gross_salary=line.gross_salary,
                daily_rate=daily_rate_from_total(line.gross_salary),
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
