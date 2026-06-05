"""
قاعدة الشهر للحسابات المالية — 30 يوماً دائماً.

تُستخدم في: مسير الرواتب، الغياب، الإجازات، نهاية الخدمة، المخصصات، وغيرها.
تواريخ الفترة (بداية/نهاية الشهر التقويمية) تبقى تقويمية لتصفية البنود فقط.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

STANDARD_MONTH_DAYS = 30


def salary_month_days(year=None, month=None) -> int:
    """عدد أيام الشهر في قسمة الراتب (ثابت 30)."""
    return STANDARD_MONTH_DAYS


def daily_rate_from_total(total) -> Decimal:
    """الأجر اليومي = إجمالي الراتب ÷ 30."""
    return (Decimal(total or 0) / Decimal(STANDARD_MONTH_DAYS)).quantize(Decimal('0.01'))


def deduction_for_days(total, days) -> Decimal:
    """خصم أيام (غياب / إجازة بدون راتب) = أجر اليوم × عدد الأيام."""
    return (daily_rate_from_total(total) * Decimal(days or 0)).quantize(Decimal('0.01'))


def calendar_month_last_day(year: int, month: int) -> date:
    """آخر يوم تقويمي في الشهر (للفترات والأرشفة)."""
    return date(year, month, monthrange(year, month)[1])


def calendar_period_bounds(year: int, month: int) -> tuple[date, date]:
    """(أول يوم، آخر يوم تقويمي) لتصفية غياب/إجازة/مخالفات الشهر."""
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)
