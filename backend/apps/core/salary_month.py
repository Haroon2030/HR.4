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
from decimal import ROUND_HALF_UP, Decimal

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
    """
    خصم أيام (غياب / إجازة بدون راتب) = الإجمالي × الأيام ÷ 30.

    الضرب قبل القسمة (بدون تقريب أجر اليوم أولاً) كي يساوي خصمُ 30 يوماً الراتبَ تماماً.
    """
    return (
        Decimal(total or 0) * Decimal(days or 0) / Decimal(STANDARD_MONTH_DAYS)
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def month_day_span(start: date, end: date, period_start: date, period_end: date) -> Decimal:
    """
    عدد الأيام ضمن شهر على قاعدة «الشهر = 30 يوماً لكل الشهور».

    - البداية: أول الشهر ⇒ اليوم 1، وإلا رقم اليوم (بحد أقصى 30).
    - النهاية: آخر الشهر (28/29/30/31) ⇒ اليوم 30، وإلا رقم اليوم (بحد أقصى 30).
    فالشهر الكامل = 30 يوماً دائماً (فبراير ويناير سواء)، والجزئي يُحسب بأرقام الأيام.
    """
    s = max(start, period_start)
    e = min(end, period_end)
    if e < s:
        return Decimal('0')
    first = 1 if s <= period_start else min(s.day, STANDARD_MONTH_DAYS)
    last = STANDARD_MONTH_DAYS if e >= period_end else min(e.day, STANDARD_MONTH_DAYS)
    return Decimal(max(last - first + 1, 0))


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


def leave_rates(annual_days=None) -> tuple[Decimal, Decimal]:
    """(أيام السنة أول 5 سنوات، أيام السنة بعدها) — بعد 5 سنوات الأعلى من الاستحقاق و30."""
    first = Decimal(annual_days or ANNUAL_LEAVE_DAYS_FIRST_TIER)
    return first, max(first, ANNUAL_LEAVE_DAYS_AFTER_FIVE)


def _fmt_days(value: Decimal) -> str:
    """1.75 / 2.5 / 2.08 — بدون أصفار زائدة."""
    return format(value.quantize(LEAVE_DAYS_QUANT).normalize(), 'f')


def accrued_annual_leave_days(
    hire_date: date,
    as_of: date,
    *,
    flat_21_only: bool = False,
    annual_days=None,
) -> Decimal:
    """
    أيام الإجازة المستحقة (annual_days = استحقاق الموظف السنوي، الافتراضي 21):
    - أشهر الخدمة المكتملة × (annual_days ÷ 12) أول 5 سنوات / 60 شهراً
    - بعدها: annual_days × 5 + الأشهر الزائدة × (الأعلى من annual_days و30) ÷ 12
    - نهاية التجربة (flat_21_only): annual_days ÷ 12 لكل شهر دائماً
    """
    months = completed_employment_months(hire_date, as_of)
    if months <= 0:
        return Decimal('0.00')
    first, later = leave_rates(annual_days)

    if flat_21_only or months <= FIRST_TIER_MONTHS:
        return (Decimal(months) * first / 12).quantize(LEAVE_DAYS_QUANT)

    extra_months = months - FIRST_TIER_MONTHS
    accrued = first * 5 + Decimal(extra_months) * later / 12
    return accrued.quantize(LEAVE_DAYS_QUANT)


def add_calendar_months(d: date, months: int) -> date:
    """تاريخ بعد عدد من الأشهر التقويمية (يُقصّ اليوم لآخر الشهر عند الحاجة)."""
    years, month_index = divmod(d.month - 1 + months, 12)
    year = d.year + years
    month = month_index + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def partial_month_leave_days(hire_date: date, as_of: date) -> int:
    """أيام الشهر الجزئي الأخير بعد آخر شهر خدمة مكتمل (لا تُسقَط في التصفية)."""
    months = completed_employment_months(hire_date, as_of)
    anchor = add_calendar_months(hire_date, months)
    return max((as_of - anchor).days, 0)


def accrued_leave_days_with_partial_month(
    hire_date: date,
    as_of: date,
    *,
    flat_21_only: bool = False,
    annual_days=None,
) -> Decimal:
    """
    أيام الإجازة المستحقة للتصفية: الأشهر المكتملة × (الاستحقاق ÷ 12)
    + أيام الشهر الجزئي × الاستحقاق ÷ 360 — فلا يضيع الشهر غير المكتمل،
    وتبقى السنة الكاملة = الاستحقاق السنوي بالضبط (21 افتراضياً).
    """
    if as_of <= hire_date:
        return Decimal('0.00')
    months = completed_employment_months(hire_date, as_of)
    full = accrued_annual_leave_days(
        hire_date, as_of, flat_21_only=flat_21_only, annual_days=annual_days,
    )
    partial = partial_month_leave_days(hire_date, as_of)
    first, later = leave_rates(annual_days)
    annual = first if (flat_21_only or months < FIRST_TIER_MONTHS) else later
    return (full + Decimal(partial) * annual / Decimal(STANDARD_YEAR_DAYS)).quantize(LEAVE_DAYS_QUANT)


def leave_accrual_formula_label(*, flat_21_only: bool = False, months: int = 0, annual_days=None) -> str:
    """نص قاعدة الاستحقاق للعرض في التقارير."""
    first, later = leave_rates(annual_days)
    first_txt = _fmt_days(first)
    monthly = _fmt_days(first / 12)
    if flat_21_only:
        return f'{first_txt} يوم/سنة = {monthly} يوم/شهر (شهر = {STANDARD_MONTH_DAYS} يوماً)'
    if months <= FIRST_TIER_MONTHS:
        return (
            f'{first_txt} يوم/سنة = {monthly} يوم/شهر '
            f'(أول 5 سنوات — شهر = {STANDARD_MONTH_DAYS} يوماً)'
        )
    return (
        f'{_fmt_days(first * 5)} يوم (5 سنوات) + {_fmt_days(later / 12)} يوم/شهر '
        f'× الأشهر الزائدة'
    )


def calendar_month_last_day(year: int, month: int) -> date:
    """آخر يوم تقويمي في الشهر (للفترات والأرشفة)."""
    return date(year, month, monthrange(year, month)[1])


def calendar_period_bounds(year: int, month: int) -> tuple[date, date]:
    """(أول يوم، آخر يوم تقويمي) لتصفية غياب/إجازة/مخالفات الشهر."""
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)
