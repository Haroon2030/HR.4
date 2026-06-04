"""تخزين مؤقت لتقارير الويب — Redis أو LocMem حسب الإعدادات."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from django.core.cache import cache

REPORT_CACHE_TTL = 300
ATTENDANCE_DAILY_CACHE_TTL = 120
CACHE_PREFIX_REPORT = 'hr:report:'
CACHE_PREFIX_ATTENDANCE_DAILY = 'hr:att_daily:'


def filters_digest(filters: dict) -> str:
    """بصمة ثابتة لفلاتر التقرير."""
    normalized = {str(k): filters[k] for k in sorted(filters)}
    raw = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]


def cache_bypass_requested(request) -> bool:
    return (request.GET.get('refresh') or '').strip() == '1'


def report_cache_key(user_id: int, report_type: str, filters: dict) -> str:
    return f'{CACHE_PREFIX_REPORT}{user_id}:{report_type}:{filters_digest(filters)}'


def get_or_build_report_data(
    *,
    user_id: int,
    report_type: str,
    filters: dict,
    builder: Callable[[], dict],
    bypass: bool = False,
) -> tuple[dict, bool]:
    """
    يُرجع (data, from_cache).
    """
    if bypass:
        data = builder()
        key = report_cache_key(user_id, report_type, filters)
        cache.set(key, data, REPORT_CACHE_TTL)
        return data, False

    key = report_cache_key(user_id, report_type, filters)
    cached = cache.get(key)
    if cached is not None:
        return cached, True

    data = builder()
    cache.set(key, data, REPORT_CACHE_TTL)
    return data, False


def attendance_daily_cache_key(user_id: int, filters: dict) -> str:
    return f'{CACHE_PREFIX_ATTENDANCE_DAILY}{user_id}:{filters_digest(filters)}'


def get_or_build_daily_attendance_rows(
    *,
    user_id: int,
    filters: dict,
    builder: Callable[[], list],
    bypass: bool = False,
) -> tuple[list, bool]:
    """تخزين صفوف التقرير اليومي بين صفحات الترقيم."""
    if bypass:
        rows = builder()
        cache.set(attendance_daily_cache_key(user_id, filters), rows, ATTENDANCE_DAILY_CACHE_TTL)
        return rows, False

    key = attendance_daily_cache_key(user_id, filters)
    cached = cache.get(key)
    if cached is not None:
        return cached, True

    rows = builder()
    cache.set(key, rows, ATTENDANCE_DAILY_CACHE_TTL)
    return rows, False


def invalidate_user_report_caches(user_id: int) -> None:
    """إبطال تقارير مستخدم — best-effort (يتطلب Redis delete_pattern أو TTL)."""
    # LocMem لا يدعم الأنماط؛ الاعتماد على TTL كافٍ لمعظم الحالات.
    _ = user_id
