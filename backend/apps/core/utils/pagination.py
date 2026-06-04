"""أدوات ترقيم آمنة للويب — منع طلبات per_page ضخمة."""

from __future__ import annotations


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
