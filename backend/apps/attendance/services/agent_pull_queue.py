"""طلبات سحب من الويب — ينفّذها وكيل الفرع (السيرفر لا يصل لـ LAN)."""
from __future__ import annotations

from datetime import date
from typing import Any

from django.core.cache import cache
from django.utils import timezone

_CACHE_LIST = 'attendance:agent_pull_pending'
_CACHE_DEVICE = 'attendance:agent_pull:{device_id}'
_TTL = 3600


def _device_key(device_id: int) -> str:
    return _CACHE_DEVICE.format(device_id=device_id)


def queue_pull_request(
    device_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    requested_by_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'device_id': device_id,
        'date_from': date_from.isoformat() if date_from else None,
        'date_to': date_to.isoformat() if date_to else None,
        'requested_at': timezone.now().isoformat(),
        'requested_by_id': requested_by_id,
    }
    cache.set(_device_key(device_id), payload, _TTL)
    pending: list[int] = list(cache.get(_CACHE_LIST) or [])
    if device_id not in pending:
        pending.append(device_id)
    cache.set(_CACHE_LIST, pending, _TTL)
    return payload


def get_pull_request(device_id: int) -> dict[str, Any] | None:
    return cache.get(_device_key(device_id))


def list_pending_pull_requests() -> list[dict[str, Any]]:
    pending_ids: list[int] = list(cache.get(_CACHE_LIST) or [])
    rows: list[dict[str, Any]] = []
    for device_id in pending_ids:
        row = get_pull_request(device_id)
        if row:
            rows.append(row)
    return rows


def queue_lan_device_sync(
    device,
    *,
    requested_by_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[bool, str]:
    """LAN devices: queue sync for branch agent. Returns (queued, message)."""
    from apps.attendance.validators import cloud_pull_blocked_message

    if not cloud_pull_blocked_message(device, force_mock=False):
        return False, ''
    queue_pull_request(
        device.pk,
        date_from=date_from,
        date_to=date_to,
        requested_by_id=requested_by_id,
    )
    return True, (
        f'تم إرسال طلب مزامنة لجهاز «{device.name}». '
        'يُنفَّذ خلال دقائق من PC الفرع (C:\\biometric_bridge).'
    )


def acknowledge_pull_request(device_id: int) -> None:
    cache.delete(_device_key(device_id))
    pending: list[int] = list(cache.get(_CACHE_LIST) or [])
    if device_id in pending:
        pending = [i for i in pending if i != device_id]
        if pending:
            cache.set(_CACHE_LIST, pending, _TTL)
        else:
            cache.delete(_CACHE_LIST)
