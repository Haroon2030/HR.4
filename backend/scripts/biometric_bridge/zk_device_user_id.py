"""تحويل رقم مستخدم الجهاز — نسخة الوكيل المحلي (تطابق attendance.services.zk_device_user_id)."""
from __future__ import annotations

import re

_DEVICE_USER_ID_RE = re.compile(r'^(\d+)')


def parse_device_user_id(raw, *, uid_fallback=None) -> int | None:
    for candidate in (raw, uid_fallback):
        if candidate is None:
            continue
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, int):
            return candidate if candidate > 0 else None
        text = str(candidate).strip()
        if not text:
            continue
        if text.isdigit():
            value = int(text)
            return value if value > 0 else None
        match = _DEVICE_USER_ID_RE.match(text)
        if match:
            value = int(match.group(1))
            return value if value > 0 else None
    return None
