"""مفاتيح وكيل البصمة — توليد وتخزين آمن (hash) والتحقق."""
from __future__ import annotations

import hashlib
import secrets

from django.utils.crypto import constant_time_compare


def hash_agent_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.strip().encode('utf-8')).hexdigest()


def generate_agent_key() -> str:
    return secrets.token_urlsafe(32)


def set_device_agent_key(device, raw_key: str | None = None) -> str:
    """يُعيّن مفتاحاً جديداً للجهاز ويُرجع النص الخام (يُعرض مرة واحدة)."""
    raw = (raw_key or generate_agent_key()).strip()
    device.agent_api_key = hash_agent_key(raw)
    device.save(update_fields=['agent_api_key', 'updated_at'])
    return raw


def verify_agent_key(device, provided: str) -> bool:
    stored = (device.agent_api_key or '').strip()
    if not stored or not provided:
        return False
    return constant_time_compare(stored, hash_agent_key(provided))


def find_device_by_agent_key(provided: str):
    """يُرجع BiometricDevice النشط المطابق للمفتاح، أو None."""
    from apps.attendance.models import BiometricDevice

    digest = hash_agent_key(provided)
    return (
        BiometricDevice.objects.filter(
            is_deleted=False,
            is_active=True,
            agent_api_key=digest,
        )
        .select_related('branch')
        .first()
    )
