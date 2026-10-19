"""فلترة قائمة الموظفين (فرع، قسم، شركة كفالة، تاريخ مباشرة) — مشتركة بين القائمة والتصدير."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from django.db.models import QuerySet


def _int_or_none(value) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _date_or_none(value) -> date | None:
    text = (str(value or '')).strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def parse_employee_list_filters(params) -> dict:
    """يقرأ فلاتر القائمة من GET: branch, department, sponsorship, from, to."""
    return {
        'branch_id': _int_or_none(params.get('branch')),
        'department_id': _int_or_none(params.get('department')),
        'sponsorship_id': _int_or_none(params.get('sponsorship')),
        'date_from': _date_or_none(params.get('from')),
        'date_to': _date_or_none(params.get('to')),
    }


def apply_employee_list_filters(qs: QuerySet, filters: dict) -> QuerySet:
    if filters.get('branch_id'):
        qs = qs.filter(branch_id=filters['branch_id'])
    if filters.get('department_id'):
        qs = qs.filter(department_id=filters['department_id'])
    if filters.get('sponsorship_id'):
        qs = qs.filter(sponsorship_id=filters['sponsorship_id'])
    if filters.get('date_from'):
        qs = qs.filter(hire_date__gte=filters['date_from'])
    if filters.get('date_to'):
        qs = qs.filter(hire_date__lte=filters['date_to'])
    return qs


def employee_list_querystring(q: str, filters: dict) -> str:
    """سلسلة استعلام بالفلاتر الفعّالة فقط (للترقيم وروابط التصدير)."""
    pairs = []
    if q:
        pairs.append(('q', q))
    for key, param in (
        ('branch_id', 'branch'),
        ('department_id', 'department'),
        ('sponsorship_id', 'sponsorship'),
    ):
        if filters.get(key):
            pairs.append((param, filters[key]))
    if filters.get('date_from'):
        pairs.append(('from', filters['date_from'].isoformat()))
    if filters.get('date_to'):
        pairs.append(('to', filters['date_to'].isoformat()))
    return urlencode(pairs)


def active_filter_count(q: str, filters: dict) -> int:
    return int(bool(q)) + sum(1 for v in filters.values() if v)
