"""طلبات سحب من الويب — ينفّذها وكيل الفرع (السيرفر لا يصل لـ LAN)."""
from __future__ import annotations

from datetime import date
from typing import Any

from django.utils import timezone

_TTL_SECONDS = 3600


def _row_to_payload(row) -> dict[str, Any]:
    return {
        'device_id': row.device_id,
        'date_from': row.date_from.isoformat() if row.date_from else None,
        'date_to': row.date_to.isoformat() if row.date_to else None,
        'requested_at': row.created_at.isoformat(),
        'requested_by_id': row.requested_by_id,
    }


def queue_pull_request(
    device_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    requested_by_id: int | None = None,
) -> dict[str, Any]:
    from apps.attendance.models import BiometricPullRequest

    pending = BiometricPullRequest.objects.filter(
        device_id=device_id,
        acknowledged_at__isnull=True,
        is_deleted=False,
    ).order_by('-created_at').first()

    if pending:
        pending.date_from = date_from
        pending.date_to = date_to
        if requested_by_id:
            pending.requested_by_id = requested_by_id
        pending.save(update_fields=['date_from', 'date_to', 'requested_by_id', 'updated_at'])
        row = pending
    else:
        row = BiometricPullRequest.objects.create(
            device_id=device_id,
            date_from=date_from,
            date_to=date_to,
            requested_by_id=requested_by_id,
        )

    _sync_cache_from_db()
    return _row_to_payload(row)


def get_pull_request(device_id: int) -> dict[str, Any] | None:
    from apps.attendance.models import BiometricPullRequest

    row = BiometricPullRequest.objects.filter(
        device_id=device_id,
        acknowledged_at__isnull=True,
        is_deleted=False,
    ).order_by('-created_at').first()
    return _row_to_payload(row) if row else None


def list_pending_pull_requests(*, device_id: int | None = None) -> list[dict[str, Any]]:
    from apps.attendance.models import BiometricPullRequest

    qs = BiometricPullRequest.objects.filter(
        acknowledged_at__isnull=True,
        is_deleted=False,
    ).select_related('device').order_by('device_id', '-created_at')
    if device_id is not None:
        qs = qs.filter(device_id=device_id)
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for row in qs:
        if row.device_id in seen:
            continue
        seen.add(row.device_id)
        rows.append(_row_to_payload(row))
    return rows


def acknowledge_pull_request(device_id: int) -> None:
    from apps.attendance.models import BiometricPullRequest

    now = timezone.now()
    BiometricPullRequest.objects.filter(
        device_id=device_id,
        acknowledged_at__isnull=True,
        is_deleted=False,
    ).update(acknowledged_at=now, updated_at=now)
    _sync_cache_from_db()


def queue_lan_device_sync(
    device,
    *,
    requested_by_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[bool, str]:
    """LAN devices: queue sync for branch agent. Returns (queued, message)."""
    from apps.attendance.validators import cloud_pull_blocked_message, is_private_lan_ip

    if not cloud_pull_blocked_message(device, force_mock=False):
        return False, ''

    if is_private_lan_ip(str(device.ip_address)) and not (device.agent_api_key or '').strip():
        return False, (
            f'جهاز «{device.name}» (ID={device.pk}) بدون مفتاح وكيل. '
            'ولّد «مفتاح وكيل» أولاً وضبطه في config.env على PC الفرع.'
        )

    queue_pull_request(
        device.pk,
        date_from=date_from,
        date_to=date_to,
        requested_by_id=requested_by_id,
    )
    return True, (
        f'تم إرسال طلب مزامنة لجهاز «{device.name}» (ID={device.pk}). '
        'يُنفَّذ خلال دقائق من PC الفرع — تأكد أن run_agent.bat يعمل.'
    )


def _sync_cache_from_db() -> None:
    """مزامنة اختيارية مع cache للتوافق — المصدر الأساسي قاعدة البيانات."""
    try:
        from django.core.cache import cache

        pending_ids = [
            row['device_id']
            for row in list_pending_pull_requests()
        ]
        if pending_ids:
            cache.set('attendance:agent_pull_pending', pending_ids, _TTL_SECONDS)
        else:
            cache.delete('attendance:agent_pull_pending')
    except Exception:
        pass
