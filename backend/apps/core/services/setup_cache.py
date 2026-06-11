"""تخزين مؤقت لجداول الإعداد (الهيكل التنظيمي) — بيانات نادرة التغيير."""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

CACHE_PREFIX = 'hr:setup:'
DEFAULT_TTL = 3600


def _ttl() -> int:
    return int(getattr(settings, 'SETUP_CACHE_TTL', DEFAULT_TTL))


def _key(name: str) -> str:
    return f'{CACHE_PREFIX}{name}'


def invalidate_setup_cache(*names: str) -> None:
    for name in names:
        cache.delete(_key(name))
    if not names:
        for n in (
            'nationalities', 'professions', 'sponsorships', 'insurances',
            'insurance_classes', 'buildings', 'banks', 'administrations',
            'active_branches', 'departments_all', 'cost_centers_all',
        ):
            cache.delete(_key(n))


def get_cached_list(cache_name: str, builder):
    """builder() → list من queryset."""
    key = _key(cache_name)
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = list(builder())
    cache.set(key, data, _ttl())
    return data
