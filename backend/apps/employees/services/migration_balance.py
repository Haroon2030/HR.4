"""ترحيل الأرصدة الافتتاحية — فصل احتساب الإجازة عن تاريخ المباشرة الحقيقي."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings

from apps.core.salary_month import (
    ANNUAL_LEAVE_DAYS_FIRST_TIER,
    calendar_month_last_day,
    LEAVE_DAYS_QUANT,
    STANDARD_YEAR_DAYS,
)


def parse_cutover_date(value: str | None = None) -> date | None:
    raw = (value if value is not None else getattr(settings, 'HR_MIGRATION_CUTOVER_DATE', '') or '').strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def global_cutover_date() -> date | None:
    return parse_cutover_date()


def employee_uses_opening_leave_balance(employee) -> bool:
    """وضع الرصيد الافتتاحي: تراكم من تاريخ الاحتساب + الرصيد الافتتاحي."""
    return bool(getattr(employee, 'leave_accrual_start_date', None))


def employee_uses_migration_balance(employee) -> bool:
    """اسم تاريخي — يُفعَّل عند وجود تاريخ احتساب إجازة."""
    return employee_uses_opening_leave_balance(employee)


def employee_leave_accrual_start(employee) -> date | None:
    return getattr(employee, 'leave_accrual_start_date', None) or None


def should_accrue_leave_in_period(employee, period_year: int, period_month: int) -> bool:
    """هل يُضاف مخصص إجازة شهري لهذا الشهر؟ (بعد تاريخ الانتقال للموظفين المُرحّلين)"""
    if not employee_uses_migration_balance(employee):
        return True
    start = employee_leave_accrual_start(employee)
    if not start:
        return True
    period_end = calendar_month_last_day(period_year, period_month)
    return period_end >= start


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 فبراير
        return d.replace(year=d.year + years, day=28)


def compute_period_leave_accrual_days(
    employee,
    *,
    as_of: date,
    flat_21_only: bool = False,
) -> Decimal:
    """
    تراكم الإجازة بالأيام من تاريخ الاحتساب (من) إلى تاريخ النهاية (إلى) أو as_of
    (الأقل منهما) — شامل اليومين، بمعدل 21 يوم/360 يوم (أول 5 سنوات) ثم 30/360.
    """
    start = employee_leave_accrual_start(employee)
    end = getattr(employee, 'leave_accrual_end_date', None)
    if end and as_of > end:
        as_of = end
    if not start or as_of < start:
        return Decimal('0.00')

    year_days = Decimal(STANDARD_YEAR_DAYS)
    tier_end = _add_years(start, 5)  # أول يوم بعد 5 سنوات
    if flat_21_only or as_of < tier_end:
        first_days, later_days = (as_of - start).days + 1, 0
    else:
        first_days = (tier_end - start).days
        later_days = (as_of - tier_end).days + 1

    accrued = (
        Decimal(first_days) * ANNUAL_LEAVE_DAYS_FIRST_TIER
        + Decimal(later_days) * Decimal('30')
    ) / year_days
    return accrued.quantize(LEAVE_DAYS_QUANT)


def compute_opening_leave_days(employee) -> Decimal:
    return Decimal(getattr(employee, 'opening_leave_days', None) or 0).quantize(LEAVE_DAYS_QUANT)


def compute_opening_eosb_amount(employee) -> Decimal:
    from decimal import ROUND_HALF_UP
    return Decimal(getattr(employee, 'opening_eosb_amount', None) or 0).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
