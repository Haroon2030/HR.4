"""حدود نطاق التاريخ لتقارير الحضور — حماية الذاكرة."""
from __future__ import annotations

from datetime import datetime, timedelta


MAX_ATTENDANCE_REPORT_DAYS = 93


def clamp_attendance_date_range(
    filters: dict,
    *,
    max_days: int = MAX_ATTENDANCE_REPORT_DAYS,
) -> tuple[dict, bool]:
    """
    يقصّ الفترة بين date_from و date_to إلى max_days يوماً (من النهاية).
    يُرجع (filters محدّثة, هل تم القص).
    """
    raw_from = filters.get('date_from')
    raw_to = filters.get('date_to')
    if not raw_from or not raw_to:
        return filters, False
    try:
        date_from = datetime.strptime(raw_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(raw_to, '%Y-%m-%d').date()
    except ValueError:
        return filters, False
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    span = (date_to - date_from).days
    if span <= max_days:
        return filters, False
    date_from = date_to - timedelta(days=max_days)
    updated = {**filters, 'date_from': date_from.isoformat(), 'date_to': date_to.isoformat()}
    return updated, True
