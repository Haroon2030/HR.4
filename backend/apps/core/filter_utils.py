"""أدوات فلترة مشتركة — قوائم متعددة وخيار «الكل»."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


def parse_multi_filter_ids(
    request,
    param: str,
    *,
    accessible_ids: set[int] | list[int] | None = None,
) -> list[int] | None:
    """
    قراءة معرّفات من GET/POST (قائمة متعددة أو قيمة واحدة قديمة).
    None = الكل (بدون فلترة).
    """
    # طلبات POST: Django يوفّر GET و POST معاً — نقرأ POST أولاً وإلا تُفقد القيم.
    source = request.POST if getattr(request, 'method', '').upper() == 'POST' else request.GET
    raw = list(source.getlist(param))
    if not raw:
        single = source.get(param)
        if single:
            raw = [single]

    ids: list[int] = []
    for v in raw:
        s = (str(v) if v is not None else '').strip()
        if not s or s.lower() == 'all':
            continue
        if s.isdigit():
            ids.append(int(s))

    if not ids:
        return None

    if accessible_ids is not None:
        allowed = set(accessible_ids)
        ids = [i for i in ids if i in allowed]
        if not ids:
            return None
    # إزالة التكرار (نموذج + حقول مخفية أو branch_id مكرر في الرابط)
    return list(dict.fromkeys(ids))


def apply_branch_filter(qs, branch_ids: list[int] | None, *, field: str = 'branch_id'):
    if branch_ids:
        return qs.filter(**{f'{field}__in': branch_ids})
    return qs


def append_multi_param(params: list[tuple[str, Any]], param: str, ids: list[int] | None) -> None:
    if ids:
        for i in ids:
            params.append((param, i))


def multi_filter_querystring(
    base: dict | None = None,
    *,
    branch_ids: list[int] | None = None,
    branch_param: str = 'branch',
    extra: dict | None = None,
) -> str:
    pairs: list[tuple[str, Any]] = []
    if base:
        for k, v in base.items():
            if v is not None and v != '':
                pairs.append((k, v))
    append_multi_param(pairs, branch_param, branch_ids)
    if extra:
        for k, v in extra.items():
            if v is not None and v != '':
                pairs.append((k, v))
    return urlencode(pairs, doseq=True)
