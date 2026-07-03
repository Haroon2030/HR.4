"""أدوات ترقيم آمنة للويب — منع طلبات per_page ضخمة + ترقيم مفتاحي بدون COUNT(*)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.core.cache import cache
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def clamp_page_size(
    raw_value,
    *,
    default: int = 50,
    maximum: int = 200,
    minimum: int = 1,
) -> int:
    """تحويل per_page من GET إلى قيمة ضمن نطاق مسموح."""
    try:
        size = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(size, maximum))


def queryset_count_cache_key(qs: QuerySet, *, prefix: str = 'qs_count') -> str:
    """مفتاح تخزين مؤقت لعدد الاستعلام — يعتمد على SQL وليس البيانات."""
    sql = str(qs.query)
    digest = hashlib.sha256(sql.encode('utf-8')).hexdigest()[:24]
    return f'{prefix}:{digest}'


def get_cached_queryset_count(
    qs: QuerySet,
    *,
    ttl: int = 60,
    prefix: str = 'qs_count',
) -> int:
    """COUNT مع تخزين مؤقت قصير — يقلل ضغط COUNT(*) على الجداول الكبيرة."""
    key = queryset_count_cache_key(qs, prefix=prefix)
    cached = cache.get(key)
    if cached is not None:
        return int(cached)
    count = qs.count()
    cache.set(key, count, ttl)
    return count


def encode_keyset_cursor(punched_at: datetime, record_id: int) -> str:
    aware = punched_at
    if timezone.is_naive(aware):
        aware = timezone.make_aware(aware, timezone.get_current_timezone())
    return f'{aware.isoformat()}|{record_id}'


def decode_keyset_cursor(raw: str | None) -> tuple[datetime, int] | None:
    if not raw:
        return None
    parts = raw.strip().split('|', 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    dt = parse_datetime(parts[0])
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt, int(parts[1])


@dataclass
class KeysetPaginator:
    """محاكاة واجهة Paginator لقوالب Django — بدون num_pages إلزامي."""

    per_page: int
    count: int | None = None

    @property
    def num_pages(self) -> int:
        if self.count is None:
            return 0
        if self.count <= 0:
            return 0
        return (self.count + self.per_page - 1) // self.per_page


@dataclass
class KeysetPage:
    """صفحة ترقيم مفتاحي — متوافقة مع hr_pagination وقوالب السجلات."""

    object_list: list[Any]
    paginator: KeysetPaginator
    has_next: bool
    has_previous: bool
    offset: int = 0
    cursor_after: str | None = None
    cursor_before: str | None = None

    def __iter__(self):
        return iter(self.object_list)

    def __len__(self) -> int:
        return len(self.object_list)

    @property
    def has_other_pages(self) -> bool:
        return self.has_next or self.has_previous

    @property
    def start_index(self) -> int:
        if not self.object_list:
            return 0
        return self.offset + 1

    @property
    def end_index(self) -> int:
        return self.offset + len(self.object_list)

    @property
    def number(self) -> int:
        if self.per_page <= 0:
            return 1
        return (self.offset // self.per_page) + 1

    @property
    def per_page(self) -> int:
        return self.paginator.per_page


def keyset_paginate_queryset(
    qs: QuerySet,
    *,
    per_page: int,
    after: str | None = None,
    before: str | None = None,
    ordering: tuple[str, ...] = ('-punched_at', '-id'),
    count_ttl: int = 60,
) -> KeysetPage:
    """
    ترقيم مفتاحي لسجلات مرتبة تنازلياً بـ (punched_at, id).
    after — الصفحة التالية؛ before — الصفحة السابقة.
    """
    per_page = max(1, min(per_page, 500))
    base_qs = qs.order_by(*ordering)

    if before:
        decoded = decode_keyset_cursor(before)
        if not decoded:
            return keyset_paginate_queryset(qs, per_page=per_page, count_ttl=count_ttl)
        punched_at, record_id = decoded
        chunk_qs = base_qs.filter(
            Q(punched_at__gt=punched_at) | Q(punched_at=punched_at, id__gt=record_id)
        ).order_by('punched_at', 'id')[: per_page + 1]
        chunk = list(chunk_qs)
        has_previous = len(chunk) > per_page
        items = list(reversed(chunk))[:per_page]
        if has_previous and len(items) > per_page:
            items = items[-per_page:]
        has_next = True
        total_count = None
    elif after:
        decoded = decode_keyset_cursor(after)
        if not decoded:
            return keyset_paginate_queryset(qs, per_page=per_page, count_ttl=count_ttl)
        punched_at, record_id = decoded
        chunk = list(
            base_qs.filter(
                Q(punched_at__lt=punched_at) | Q(punched_at=punched_at, id__lt=record_id)
            )[: per_page + 1]
        )
        has_next = len(chunk) > per_page
        items = chunk[:per_page]
        has_previous = True
        total_count = None
    else:
        chunk = list(base_qs[: per_page + 1])
        has_next = len(chunk) > per_page
        items = chunk[:per_page]
        has_previous = False
        total_count = get_cached_queryset_count(base_qs, ttl=count_ttl, prefix='punch_count')

    cursor_after = None
    cursor_before = None
    if items:
        last = items[-1]
        first = items[0]
        cursor_after = encode_keyset_cursor(last.punched_at, last.pk)
        cursor_before = encode_keyset_cursor(first.punched_at, first.pk)

    paginator = KeysetPaginator(per_page=per_page, count=total_count)
    return KeysetPage(
        object_list=items,
        paginator=paginator,
        has_next=has_next,
        has_previous=has_previous,
        offset=0,
        cursor_after=cursor_after,
        cursor_before=cursor_before,
    )
