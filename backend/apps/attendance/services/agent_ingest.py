"""استقبال دفعات الحضور من الوكيل المحلي."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.attendance.models import BiometricDevice, BiometricDeviceUser
from apps.attendance.services.labels import punch_type_for_status, verify_mode_label
from apps.attendance.services.punch_sync import import_raw_attendance_rows
from apps.attendance.services.zk_client import DeviceUserRow, RawAttendanceRow


@dataclass
class AgentIngestResult:
    imported: int
    skipped_duplicate: int
    skipped_time_filter: int
    skipped_out_of_bounds: int
    punches_received: int
    users_updated: int
    batch: str


AGENT_PUNCH_MAX_FUTURE_MINUTES = 10
AGENT_PUNCH_MAX_PAST_DAYS_INCREMENTAL = 93
AGENT_PUNCH_MAX_PAST_DAYS_FULL_SYNC = 365


def _parse_punched_at(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = parse_datetime(str(value))
    if dt is None:
        raise ValueError(f'وقت بصمة غير صالح: {value}')
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _is_within_punch_bounds(dt: datetime, *, incremental: bool) -> bool:
    now = timezone.now()
    if dt > now + timedelta(minutes=AGENT_PUNCH_MAX_FUTURE_MINUTES):
        return False
    max_past_days = (
        AGENT_PUNCH_MAX_PAST_DAYS_INCREMENTAL
        if incremental
        else AGENT_PUNCH_MAX_PAST_DAYS_FULL_SYNC
    )
    return dt >= now - timedelta(days=max_past_days)


def _row_from_payload(item: dict[str, Any]) -> RawAttendanceRow:
    status = item.get('raw_status')
    if status is not None:
        status = int(status)
    punch_type = (item.get('punch_type') or '').strip()
    if not punch_type and status is not None:
        punch_type, _ = punch_type_for_status(status)
    return RawAttendanceRow(
        device_user_id=int(item['device_user_id']),
        punched_at=_parse_punched_at(item['punched_at']),
        punch_type=punch_type or 'unknown',
        verify_mode=int(item['verify_mode']) if item.get('verify_mode') is not None else None,
        status=status,
        uid=int(item['device_record_uid']) if item.get('device_record_uid') is not None else None,
    )


def _sync_users_from_payload(device: BiometricDevice, users: list[dict[str, Any]]) -> int:
    if not users:
        return 0
    now = timezone.now()
    with transaction.atomic():
        for item in users:
            user_id = int(item['device_user_id'])
            defaults = {
                'name': (item.get('name') or '').strip(),
                'card': str(item.get('card') or ''),
                'last_synced_at': now,
            }
            if item.get('privilege') is not None:
                defaults['privilege'] = int(item['privilege'])
            BiometricDeviceUser.objects.update_or_create(
                device=device,
                device_user_id=user_id,
                defaults=defaults,
            )
    return len(users)


def ingest_agent_payload(
    device: BiometricDevice,
    *,
    punches: list[dict[str, Any]],
    users: list[dict[str, Any]] | None = None,
    incremental: bool = True,
) -> AgentIngestResult:
    if not device.is_active:
        raise ValueError('الجهاز غير نشط.')
    if device.is_deleted:
        raise ValueError('الجهاز محذوف.')

    users_updated = _sync_users_from_payload(device, users or [])

    name_map = {
        u.device_user_id: u.name
        for u in BiometricDeviceUser.objects.filter(device=device, is_deleted=False).only(
            'device_user_id', 'name',
        )
        if u.name
    }
    for item in users or []:
        uid = int(item['device_user_id'])
        name = (item.get('name') or '').strip()
        if name:
            name_map[uid] = name

    from apps.attendance.models import EmployeeBiometricEnrollment

    enroll_map = {
        e.device_user_id: e.employee_id
        for e in EmployeeBiometricEnrollment.objects.filter(
            device=device, is_deleted=False,
        ).only('device_user_id', 'employee_id')
    }

    rows = []
    skipped_out_of_bounds = 0
    for p in punches:
        row = _row_from_payload(p)
        if not _is_within_punch_bounds(row.punched_at, incremental=incremental):
            skipped_out_of_bounds += 1
            continue
        rows.append(row)
    outcome = import_raw_attendance_rows(
        device,
        rows,
        name_map=name_map,
        enroll_map=enroll_map,
        incremental=incremental,
    )

    return AgentIngestResult(
        imported=outcome['imported'],
        skipped_duplicate=outcome['skipped'],
        skipped_time_filter=outcome.get('skipped_time_filter', 0),
        skipped_out_of_bounds=skipped_out_of_bounds,
        punches_received=len(punches),
        users_updated=users_updated,
        batch=outcome.get('batch', ''),
    )
