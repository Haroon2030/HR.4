"""إبطال ذاكرة التنقل المؤقتة (sidebar + لوحة التحكم)."""
from __future__ import annotations

from apps.core.services.dashboard_cache import invalidate_dashboard_overview
from apps.core.services.sidebar_counts import invalidate_sidebar_counts


def invalidate_user_navigation_caches(*user_ids: int | None) -> None:
    invalidate_sidebar_counts(*user_ids)
    invalidate_dashboard_overview(*user_ids)
