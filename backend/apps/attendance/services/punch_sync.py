"""
استيراد سجلات الحضور بدون تكرار — مزامنة تزايدية.

- عند السحب المتكرر: تُصفّى السجلات الأقدم من آخر بصمة محفوظة (نافذة 60 ثانية).
- منع التكرار: معرف السجل على الجهاز (uid) أو بصمة (رقم المستخدم + وقت البصمة).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

if TYPE_CHECKING:
    from apps.attendance.models import AttendancePunch, BiometricDevice
    from apps.attendance.services.attendance_pull import EnrichedPunch
    from apps.attendance.services.zk_client import RawAttendanceRow

INCREMENTAL_BUFFER = timedelta(seconds=60)


@dataclass
class DevicePunchIndex:
    """فهرس سريع لسجلات الجهاز المحفوظة مسبقاً."""

    uids: set[int] = field(default_factory=set)
    fingerprints: set[tuple[int, datetime]] = field(default_factory=set)
    watermark: datetime | None = None


class _PunchLike(Protocol):
    device_user_id: int
    punched_at: datetime
    uid: int | None


def punch_fingerprint(device_user_id: int, punched_at: datetime) -> tuple[int, datetime]:
    if timezone.is_naive(punched_at):
        punched_at = timezone.make_aware(punched_at, timezone.get_current_timezone())
    return (device_user_id, punched_at.replace(microsecond=0))


def load_device_punch_index(device_id: int) -> DevicePunchIndex:
    from apps.attendance.models import AttendancePunch

    qs = AttendancePunch.objects.filter(device_id=device_id)
    uids = {
        int(uid)
        for uid in qs.filter(device_record_uid__isnull=False).values_list(
            'device_record_uid', flat=True,
        )
    }
    fingerprints: set[tuple[int, datetime]] = set()
    for user_id, ts in qs.values_list('device_user_id', 'punched_at'):
        fingerprints.add(punch_fingerprint(int(user_id), ts))

    watermark = qs.aggregate(m=Max('punched_at'))['m']
    return DevicePunchIndex(uids=uids, fingerprints=fingerprints, watermark=watermark)


def row_is_duplicate(row: _PunchLike, index: DevicePunchIndex) -> bool:
    uid = getattr(row, 'uid', None)
    if uid is None:
        uid = getattr(row, 'device_record_uid', None)
    if uid is not None and int(uid) in index.uids:
        return True
    return punch_fingerprint(row.device_user_id, row.punched_at) in index.fingerprints


def register_row(index: DevicePunchIndex, row: _PunchLike) -> None:
    uid = getattr(row, 'uid', None)
    if uid is None:
        uid = getattr(row, 'device_record_uid', None)
    if uid is not None:
        index.uids.add(int(uid))
    index.fingerprints.add(punch_fingerprint(row.device_user_id, row.punched_at))
    if index.watermark is None or row.punched_at > index.watermark:
        index.watermark = row.punched_at


def filter_incremental_by_time(
    rows: list,
    index: DevicePunchIndex,
    *,
    incremental: bool,
) -> tuple[list, int]:
    """يُبقي فقط السجلات بعد آخر وقت محفوظ (مع هامش)."""
    if not incremental or not index.watermark or not rows:
        return rows, 0
    cut = index.watermark - INCREMENTAL_BUFFER
    before = len(rows)
    kept = [r for r in rows if r.punched_at > cut]
    return kept, before - len(kept)


def partition_new_rows(
    rows: list,
    index: DevicePunchIndex,
    *,
    incremental: bool,
) -> tuple[list, int, int]:
    """
    يُرجع: (صفوف جديدة للاستيراد, متخطى بفلتر الوقت, متخطى مكرر في DB).
    """
    candidates, skipped_time = filter_incremental_by_time(rows, index, incremental=incremental)
    new_rows: list = []
    skipped_dup = 0
    for row in candidates:
        if row_is_duplicate(row, index):
            skipped_dup += 1
            continue
        new_rows.append(row)
        register_row(index, row)
    return new_rows, skipped_time, skipped_dup


def import_enriched_punches(
    device: BiometricDevice,
    punches: list[EnrichedPunch],
    *,
    dry_run: bool,
    incremental: bool,
) -> dict:
    from apps.attendance.models import AttendancePunch
    from apps.attendance.selectors.biometric_devices import make_sync_batch_label
    from apps.attendance.services.labels import verify_mode_label as zk_verify_label

    index = load_device_punch_index(device.id)
    new_punches, skipped_time, skipped_dup = partition_new_rows(
        punches, index, incremental=incremental,
    )
    batch = make_sync_batch_label(device)

    if dry_run:
        return {
            'batch': batch,
            'imported': 0,
            'skipped_duplicate': skipped_dup,
            'skipped_time_filter': skipped_time,
            'punches_new': len(new_punches),
            'new_punches': new_punches,
        }

    valid_types = {c.value for c in AttendancePunch.PunchType}
    to_create: list[AttendancePunch] = []
    for p in new_punches:
        punch_type = p.punch_type if p.punch_type in valid_types else AttendancePunch.PunchType.UNKNOWN
        to_create.append(
            AttendancePunch(
                device=device,
                employee_id=p.employee_id,
                device_user_id=p.device_user_id,
                device_user_name=p.device_user_name,
                punched_at=p.punched_at,
                punch_type=punch_type,
                verify_mode=p.verify_mode,
                verify_mode_label=p.verify_mode_label or zk_verify_label(p.verify_mode),
                device_record_uid=p.device_record_uid,
                raw_status=p.raw_status,
                sync_batch=batch,
            )
        )

    with transaction.atomic():
        if to_create:
            AttendancePunch.objects.bulk_create(to_create, ignore_conflicts=True)

        device.connection_status = device.ConnectionStatus.ONLINE
        device.last_error = ''
        device.last_sync_at = timezone.now()
        device.last_ping_at = timezone.now()
        device.save(
            update_fields=[
                'connection_status', 'last_error', 'last_sync_at',
                'last_ping_at', 'updated_at',
            ],
        )

    return {
        'batch': batch,
        'imported': len(new_punches),
        'skipped_duplicate': skipped_dup,
        'skipped_time_filter': skipped_time,
        'punches_new': len(new_punches),
        'new_punches': new_punches,
    }


def import_raw_attendance_rows(
    device: BiometricDevice,
    rows: list[RawAttendanceRow],
    *,
    name_map: dict[int, str],
    enroll_map: dict[int, int | None],
    incremental: bool,
) -> dict:
    from apps.attendance.models import AttendancePunch
    from apps.attendance.selectors.biometric_devices import make_sync_batch_label
    from apps.attendance.services.labels import verify_mode_label

    index = load_device_punch_index(device.id)
    new_rows, skipped_time, skipped_dup = partition_new_rows(
        rows, index, incremental=incremental,
    )
    batch = make_sync_batch_label(device)
    valid_types = {c.value for c in AttendancePunch.PunchType}

    to_create: list[AttendancePunch] = []
    for row in new_rows:
        punch_type = row.punch_type if row.punch_type in valid_types else AttendancePunch.PunchType.UNKNOWN
        to_create.append(
            AttendancePunch(
                device=device,
                employee_id=enroll_map.get(row.device_user_id),
                device_user_id=row.device_user_id,
                device_user_name=name_map.get(row.device_user_id, ''),
                punched_at=row.punched_at,
                punch_type=punch_type,
                punch_type_source=AttendancePunch.PunchTypeSource.DEVICE,
                verify_mode=row.verify_mode,
                verify_mode_label=verify_mode_label(row.verify_mode),
                device_record_uid=row.uid,
                raw_status=row.status,
                sync_batch=batch,
            )
        )

    with transaction.atomic():
        if to_create:
            AttendancePunch.objects.bulk_create(to_create, ignore_conflicts=True)

        device.connection_status = device.ConnectionStatus.ONLINE
        device.last_error = ''
        device.last_sync_at = timezone.now()
        device.last_ping_at = timezone.now()
        device.save(
            update_fields=[
                'connection_status', 'last_error', 'last_sync_at',
                'last_ping_at', 'updated_at',
            ],
        )

    return {
        'batch': batch,
        'imported': len(new_rows),
        'skipped': skipped_dup,
        'skipped_time_filter': skipped_time,
        'punches_new': len(new_rows),
    }
