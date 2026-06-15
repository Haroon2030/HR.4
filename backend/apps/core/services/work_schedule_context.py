"""سياق جدول الدوام للبريد و PDF."""
from __future__ import annotations

import calendar as cal
from typing import Any

MONTHS_AR = [
    '',
    'يناير',
    'فبراير',
    'مارس',
    'أبريل',
    'مايو',
    'يونيو',
    'يوليو',
    'أغسطس',
    'سبتمبر',
    'أكتوبر',
    'نوفمبر',
    'ديسمبر',
]

WEEK_DAYS_AR = [
    'الأحد',
    'الإثنين',
    'الثلاثاء',
    'الأربعاء',
    'الخميس',
    'الجمعة',
    'السبت',
]


def _format_day_code(code: str) -> str:
    raw = (code or '').strip()
    if not raw:
        return ''
    norm = raw.lower()
    if norm in ('d', 'check', 'v') or raw == '✓':
        return '✓'
    return raw


def build_schedule_boxes_context(boxes_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """يُحوّل صناديق JSON المحفوظة إلى سياق موحّد للبريد و PDF."""
    boxes_ctx: list[dict[str, Any]] = []
    if not isinstance(boxes_data, list):
        return boxes_ctx

    for box in boxes_data:
        if not isinstance(box, dict):
            continue
        try:
            year = int(box.get('year'))
            month = int(box.get('month'))
        except (TypeError, ValueError):
            continue
        if not (1900 <= year <= 2100 and 1 <= month <= 12):
            continue

        total_days = cal.monthrange(year, month)[1]
        codes = box.get('day_codes') or {}
        if not isinstance(codes, dict):
            codes = {}

        day_cells: list[dict[str, Any]] = []
        for day in range(1, 32):
            if day > total_days:
                day_cells.append({
                    'day': day,
                    'code': '',
                    'code_display': '—',
                    'active': False,
                    'weekday': '',
                })
                continue
            wd = cal.weekday(year, month, day)
            weekday = WEEK_DAYS_AR[(wd + 1) % 7]
            raw_code = codes.get(str(day), '')
            day_cells.append({
                'day': day,
                'code': raw_code,
                'code_display': _format_day_code(raw_code) or '—',
                'active': True,
                'weekday': weekday,
            })

        days = box.get('days') or []
        if not isinstance(days, list):
            days = []
        days_sorted = sorted({int(d) for d in days if str(d).isdigit() and 1 <= int(d) <= 31})

        shift_label = (box.get('shift_label') or '').strip()
        boxes_ctx.append({
            'year': year,
            'month': month,
            'month_name': MONTHS_AR[month],
            'days': days_sorted,
            'days_count': len(days_sorted),
            'days_str': '، '.join(str(d) for d in days_sorted),
            'day_cells': day_cells,
            'shift_title': shift_label or '—',
        })

    return boxes_ctx
