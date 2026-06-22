"""
قاعدة الشهر للحسابات المالية — 30 يوماً دائماً.

تُستخدم في: مسير الرواتب، الغياب، الإجازات، نهاية الخدمة، المخصصات، وغيرها.
تواريخ الفترة (بداية/نهاية الشهر التقويمية) تبقى تقويمية لتصفية البنود فقط.

استحقاق الإجازة السنوية:
- 21 يوم/سنة (أول 5 سنوات) = 1.75 يوم لكل شهر خدمة مكتمل
- 30 يوم/سنة (من السنة السادسة) = 2.5 يوم/شهر
- السنة المحاسبية = 360 يوماً (12 × 30)
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

STANDARD_MONTH_DAYS = 30
STANDARD_YEAR_DAYS = STANDARD_MONTH_DAYS * 12  # 360

# 21 يوم إجازة سنوياً ÷ 12 شهر (شهر = 30 يوماً)
MONTHLY_LEAVE_ACCRUAL_DAYS = Decimal('21') / Decimal('12')  # 1.75
MONTHLY_LEAVE_AFTER_FIVE_YEARS = Decimal('30') / Decimal('12')  # 2.5
ANNUAL_LEAVE_DAYS_FIRST_TIER = Decimal('21')
ANNUAL_LEAVE_DAYS_AFTER_FIVE = Decimal('30')
FIRST_TIER_LEAVE_CAP = ANNUAL_LEAVE_DAYS_FIRST_TIER * Decimal('5')  # 105
FIRST_TIER_MONTHS = 60
FIRST_TIER_SERVICE_DAYS = STANDARD_YEAR_DAYS * 5  # 1800

LEAVE_DAYS_QUANT = Decimal('0.01')


def salary_month_days(year=None, month=None) -> int:
    """عدد أيام الشهر في قسمة الراتب (ثابت 30)."""
    return STANDARD_MONTH_DAYS


def daily_rate_from_total(total) -> Decimal:
    """الأجر اليومي = إجمالي الراتب ÷ 30."""
    return (Decimal(total or 0) / Decimal(STANDARD_MONTH_DAYS)).quantize(Decimal('0.01'))


def deduction_for_days(total, days) -> Decimal:
    """خصم أيام (غياب / إجازة بدون راتب) = أجر اليوم × عدد الأيام."""
    return (daily_rate_from_total(total) * Decimal(days or 0)).quantize(Decimal('0.01'))


def employment_service_days(hire_date: date, as_of: date) -> int:
    """أيام الخدمة من تاريخ المباشرة حتى التاريخ (شامل المباشرة)."""
    if as_of < hire_date:
        return 0
    return max((as_of - hire_date).days, 0)


def completed_employment_months(hire_date: date, as_of: date) -> int:
    """
    أشهر الخدمة المكتملة — تطابق إقفال مسير الرواتب (شهر تقويمي = 30 يوماً).

    - مباشرة في اليوم 1: كل شهر تقويمي يُحسب كاملاً (يناير→يناير = شهر واحد).
    - غير ذلك: الشهر يُستكمل بعد مرور يوم المباشرة في الشهر التالي.
    """
    if as_of <= hire_date:
        return 0
    months = (as_of.year - hire_date.year) * 12 + (as_of.month - hire_date.month)
    if hire_date.day == 1:
        if as_of.day != hire_date.day:
            months += 1
    elif as_of.day < hire_date.day:
        months -= 1
    return max(months, 0)


def service_years_30day(service_days: int) -> Decimal:
    """سنوات الخدمة بقاعدة السنة = 360 يوماً."""
    if service_days <= 0:
        return Decimal('0')
    return (Decimal(service_days) / Decimal(STANDARD_YEAR_DAYS)).quantize(Decimal('0.0001'))


def accrued_annual_leave_days(
    hire_date: date,
    as_of: date,
    *,
    flat_21_only: bool = False,
) -> Decimal:
    """
    أيام الإجازة المستحقة:
    - أشهر الخدمة المكتملة × 1.75 (أول 5 سنوات / 60 شهراً)
    - بعدها: 105 يوم + الأشهر الزائدة × 2.5
    - نهاية التجربة (flat_21_only): 1.75/شهر دائماً
    """
    months = completed_employment_months(hire_date, as_of)
    if months <= 0:
        return Decimal('0.00')

    if flat_21_only or months <= FIRST_TIER_MONTHS:
        return (Decimal(months) * MONTHLY_LEAVE_ACCRUAL_DAYS).quantize(LEAVE_DAYS_QUANT)

    extra_months = months - FIRST_TIER_MONTHS
    accrued = FIRST_TIER_LEAVE_CAP + (Decimal(extra_months) * MONTHLY_LEAVE_AFTER_FIVE_YEARS)
    return accrued.quantize(LEAVE_DAYS_QUANT)


def leave_accrual_formula_label(*, flat_21_only: bool = False, months: int = 0) -> str:
    """نص قاعدة الاستحقاق للعرض في التقارير."""
    if flat_21_only:
        return f'21 يوم/سنة = {MONTHLY_LEAVE_ACCRUAL_DAYS} يوم/شهر (شهر = {STANDARD_MONTH_DAYS} يوماً)'
    if months <= FIRST_TIER_MONTHS:
        return (
            f'21 يوم/سنة = {MONTHLY_LEAVE_ACCRUAL_DAYS} يوم/شهر '
            f'(أول 5 سنوات — شهر = {STANDARD_MONTH_DAYS} يوماً)'
        )
    return (
        f'{FIRST_TIER_LEAVE_CAP} يوم (5 سنوات) + {MONTHLY_LEAVE_AFTER_FIVE_YEARS} يوم/شهر '
        f'× الأشهر الزائدة'
    )


def calendar_month_last_day(year: int, month: int) -> date:
    """آخر يوم تقويمي في الشهر (للفترات والأرشفة)."""
    return date(year, month, monthrange(year, month)[1])


def calendar_period_bounds(year: int, month: int) -> tuple[date, date]:
    """(أول يوم، آخر يوم تقويمي) لتصفية غياب/إجازة/مخالفات الشهر."""
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)
