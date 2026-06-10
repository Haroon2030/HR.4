"""فترة استحقاق الراتب للموظف داخل شهر المسير — مع تاريخ المباشرة والتوقف."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.core.salary_month import calendar_period_bounds, salary_month_days


def employee_payroll_period(
    *,
    period_year: int,
    period_month: int,
    hire_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """
    يُرجع فترة الاستحقاق الفعلية داخل الشهر.

    - تاريخ البداية = max(أول الشهر, تاريخ المباشرة)
    - تاريخ الإقفال = min(آخر الشهر, تاريخ التوقف إن وُجد)
    - أيام الاستحقاق الأساسية = أيام التقويم ضمن الفترة (بحد أقصى 30 يوماً للحساب)
    """
    period_start, period_end = calendar_period_bounds(period_year, period_month)
    month_days = Decimal(salary_month_days(period_year, period_month))

    eff_start = period_start
    if hire_date:
        if hire_date > period_end:
            return _empty_period(period_start, period_end, month_days)
        if hire_date > eff_start:
            eff_start = hire_date

    eff_end = period_end
    if end_date and end_date < eff_end:
        if end_date < period_start:
            return _empty_period(period_start, period_end, month_days)
        eff_end = end_date

    if eff_end < eff_start:
        payable_base = Decimal('0')
    else:
        calendar_days = Decimal((eff_end - eff_start).days + 1)
        payable_base = min(calendar_days, month_days)

    return {
        'period_start': eff_start,
        'period_end': eff_end,
        'month_days': month_days,
        'payable_base_days': payable_base,
    }


def _empty_period(period_start: date, period_end: date, month_days: Decimal) -> dict:
    return {
        'period_start': period_start,
        'period_end': period_end,
        'month_days': month_days,
        'payable_base_days': Decimal('0'),
    }


def period_from_line_breakdown(line, run) -> dict:
    """قراءة الفترة من breakdown أو إعادة حسابها (للأسطر القديمة)."""
    raw = (line.breakdown or {}).get('period') or {}
    if raw.get('start') and raw.get('end'):
        return {
            'period_start': date.fromisoformat(raw['start']),
            'period_end': date.fromisoformat(raw['end']),
            'month_days': Decimal(raw.get('month_days') or salary_month_days(run.period_year, run.period_month)),
            'payable_base_days': Decimal(raw.get('payable_base_days') or '0'),
        }
    emp = line.employee
    return employee_payroll_period(
        period_year=run.period_year,
        period_month=run.period_month,
        hire_date=getattr(emp, 'hire_date', None),
        end_date=getattr(emp, 'end_date', None),
    )


def prorate_amount(amount, payable_base_days: Decimal, month_days: Decimal) -> Decimal:
    if month_days <= 0 or payable_base_days <= 0:
        return Decimal('0')
    return (Decimal(amount or 0) * payable_base_days / month_days).quantize(Decimal('0.01'))
