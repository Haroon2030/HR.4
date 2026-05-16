"""اتصال أجهزة ZKTeco عبر الشبكة (بروتوكول ZK — المنفذ الافتراضي 4370)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from apps.attendance.models import BiometricDevice

logger = logging.getLogger(__name__)

from apps.attendance.services.labels import punch_type_for_status, verify_mode_label


@dataclass
class DeviceProbeResult:
    ok: bool
    message: str
    serial_number: str = ''
    firmware: str = ''
    device_name: str = ''
    user_count: int = 0
    attendance_count: int = 0


@dataclass
class RawAttendanceRow:
    device_user_id: int
    punched_at: datetime
    punch_type: str
    verify_mode: int | None
    status: int | None
    uid: int | None


@dataclass
class DeviceUserRow:
    device_user_id: int
    name: str
    card: str = ''
    privilege: int | None = None


@dataclass
class DeviceSnapshot:
    users: list[DeviceUserRow]
    attendance: list[RawAttendanceRow]
    serial_number: str = ''
    firmware: str = ''


def is_mock_mode(*, force: bool | None = None) -> bool:
    if force is not None:
        return force
    return bool(getattr(settings, 'BIOMETRIC_MOCK_MODE', False))


def _zk_connect_kwargs(device: BiometricDevice, *, timeout: int | None = None) -> dict:
    return {
        'ip': device.ip_address,
        'port': device.port,
        'timeout': timeout or getattr(settings, 'BIOMETRIC_ZK_TIMEOUT', 15),
        'password': int(device.comm_key or 0),
        'force_udp': False,
        'ommit_ping': getattr(settings, 'BIOMETRIC_ZK_OMIT_PING', True),
    }


def format_zk_error(exc: Exception) -> str:
    text = str(exc).strip()
    lower = text.lower()
    if 'unauthenticated' in lower or 'auth' in lower:
        return (
            'رفض الجهاز الاتصال (Comm Key غير صحيح). '
            'من الجهاز: القائمة → Comm → PC Connection وتأكد أن كلمة الاتصال = '
            'نفس قيمة Comm Key في النظام (غالباً 0).'
        )
    if 'timed out' in lower or 'timeout' in lower:
        return f'انتهت مهلة الاتصال ({text}). تأكد أن الكمبيوتر على نفس شبكة الجهاز.'
    if 'network' in lower or 'refused' in lower or 'unreachable' in lower:
        return f'تعذّر الوصول للجهاز: {text}'
    return text or 'خطأ غير معروف في الاتصال بالجهاز'


def _import_zk():
    try:
        from zk import ZK
        from zk.exception import ZKErrorResponse, ZKNetworkError
        return ZK, ZKNetworkError, ZKErrorResponse
    except ImportError as exc:
        raise ImportError(
            'حزمة pyzk غير مثبتة. نفّذ: pip install pyzk'
        ) from exc


def _mock_attendance_rows() -> list[RawAttendanceRow]:
    now = timezone.now()
    rows: list[RawAttendanceRow] = []
    uid = 2000
    for day_offset in range(7):
        base = (now - timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        for user_id in (1, 2):
            offset_min = 5 if user_id == 2 else 0
            rows.append(RawAttendanceRow(
                user_id, base.replace(hour=8, minute=offset_min), 'in', 15, 0, uid,
            ))
            uid += 1
            rows.append(RawAttendanceRow(
                user_id, base.replace(hour=17, minute=offset_min), 'out', 15, 1, uid,
            ))
            uid += 1
    return rows


def fetch_device_snapshot(
    device: BiometricDevice,
    *,
    clear_after: bool = False,
    force_mock: bool | None = None,
) -> tuple[DeviceSnapshot | None, str | None]:
    """جلسة اتصال واحدة: مستخدمون + كل سجلات الحضور على الجهاز."""
    if is_mock_mode(force=force_mock):
        return DeviceSnapshot(
            users=[
                DeviceUserRow(1, 'أحمد محمد', '1001'),
                DeviceUserRow(2, 'خالد العتيبي', '1002'),
                DeviceUserRow(3, 'سارة القحطاني', '1003'),
            ],
            attendance=_mock_attendance_rows(),
            serial_number='MOCK-SN-001',
            firmware='Mock 1.0',
        ), None

    ZK, ZKNetworkError, ZKErrorResponse = _import_zk()
    conn = None
    try:
        kw = _zk_connect_kwargs(device)
        zk = ZK(kw['ip'], port=kw['port'], timeout=kw['timeout'], password=kw['password'],
                force_udp=kw['force_udp'], ommit_ping=kw['ommit_ping'])
        conn = zk.connect()
        users: list[DeviceUserRow] = []
        for user in conn.get_users() or []:
            user_id = getattr(user, 'user_id', None) or getattr(user, 'uid', None)
            if user_id is None:
                continue
            users.append(
                DeviceUserRow(
                    device_user_id=int(user_id),
                    name=(getattr(user, 'name', None) or '').strip(),
                    card=str(getattr(user, 'card', None) or ''),
                    privilege=getattr(user, 'privilege', None),
                )
            )

        attendance: list[RawAttendanceRow] = []
        for rec in conn.get_attendance() or []:
            ts = rec.timestamp
            if timezone.is_naive(ts):
                ts = timezone.make_aware(ts, timezone.get_current_timezone())
            status = getattr(rec, 'status', None)
            punch_type, _ = punch_type_for_status(status)
            attendance.append(
                RawAttendanceRow(
                    device_user_id=int(rec.user_id),
                    punched_at=ts,
                    punch_type=punch_type,
                    verify_mode=getattr(rec, 'punch', None),
                    status=status,
                    uid=getattr(rec, 'uid', None),
                )
            )

        if clear_after and attendance:
            conn.clear_attendance()

        serial = str(getattr(conn, 'get_serialnumber', lambda: '')() or '')
        firmware = str(getattr(conn, 'get_firmware_version', lambda: '')() or '')
        return DeviceSnapshot(users=users, attendance=attendance, serial_number=serial, firmware=firmware), None
    except (ZKNetworkError, ZKErrorResponse, OSError, TimeoutError) as exc:
        return None, format_zk_error(exc)
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def probe_device(
    device: BiometricDevice,
    *,
    timeout: int | None = None,
    force_mock: bool | None = None,
) -> DeviceProbeResult:
    if is_mock_mode(force=force_mock):
        return DeviceProbeResult(
            ok=True,
            message='وضع تجريبي محلي (BIOMETRIC_MOCK_MODE) — لا يوجد اتصال حقيقي',
            serial_number='MOCK-SN-001',
            firmware='Mock 1.0',
            device_name=device.name,
            user_count=3,
            attendance_count=12,
        )

    ZK, ZKNetworkError, ZKErrorResponse = _import_zk()
    conn = None
    try:
        kw = _zk_connect_kwargs(device, timeout=timeout)
        zk = ZK(kw['ip'], port=kw['port'], timeout=kw['timeout'], password=kw['password'],
                force_udp=kw['force_udp'], ommit_ping=kw['ommit_ping'])
        conn = zk.connect()
        return DeviceProbeResult(
            ok=True,
            message='تم الاتصال بالجهاز بنجاح',
            serial_number=str(getattr(conn, 'get_serialnumber', lambda: '')() or ''),
            firmware=str(getattr(conn, 'get_firmware_version', lambda: '')() or ''),
            device_name=str(getattr(conn, 'get_device_name', lambda: device.name)() or device.name),
            user_count=len(conn.get_users() or []),
            attendance_count=len(conn.get_attendance() or []),
        )
    except (ZKNetworkError, ZKErrorResponse, OSError, TimeoutError) as exc:
        return DeviceProbeResult(ok=False, message=format_zk_error(exc))
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def fetch_device_users(
    device: BiometricDevice,
    *,
    force_mock: bool | None = None,
) -> tuple[list[DeviceUserRow], str | None]:
    if is_mock_mode(force=force_mock):
        return [
            DeviceUserRow(1, 'أحمد محمد', '1001'),
            DeviceUserRow(2, 'خالد العتيبي', '1002'),
            DeviceUserRow(3, 'سارة القحطاني', '1003'),
        ], None

    ZK, ZKNetworkError, ZKErrorResponse = _import_zk()
    conn = None
    try:
        kw = _zk_connect_kwargs(device)
        zk = ZK(kw['ip'], port=kw['port'], timeout=kw['timeout'], password=kw['password'],
                force_udp=kw['force_udp'], ommit_ping=kw['ommit_ping'])
        conn = zk.connect()
        rows: list[DeviceUserRow] = []
        for user in conn.get_users() or []:
            user_id = getattr(user, 'user_id', None) or getattr(user, 'uid', None)
            if user_id is None:
                continue
            name = (getattr(user, 'name', None) or '').strip()
            card = str(getattr(user, 'card', None) or '')
            rows.append(
                DeviceUserRow(
                    device_user_id=int(user_id),
                    name=name,
                    card=card,
                    privilege=getattr(user, 'privilege', None),
                )
            )
        return rows, None
    except (ZKNetworkError, ZKErrorResponse, OSError, TimeoutError) as exc:
        return [], format_zk_error(exc)
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def sync_device_users(device: BiometricDevice, *, force_mock: bool | None = None) -> dict:
    from apps.attendance.models import BiometricDeviceUser, EmployeeBiometricEnrollment

    rows, error = fetch_device_users(device, force_mock=force_mock)
    if error:
        return {'ok': False, 'error': error, 'synced': 0}

    now = timezone.now()
    name_map: dict[int, str] = {}
    synced = 0
    for row in rows:
        name_map[row.device_user_id] = row.name
        BiometricDeviceUser.objects.update_or_create(
            device=device,
            device_user_id=row.device_user_id,
            defaults={
                'name': row.name,
                'card': row.card,
                'privilege': row.privilege,
                'last_synced_at': now,
            },
        )
        synced += 1

    for enrollment in EmployeeBiometricEnrollment.objects.filter(device=device):
        device_name = name_map.get(enrollment.device_user_id, '')
        if device_name and enrollment.device_user_name != device_name:
            enrollment.device_user_name = device_name
            enrollment.save(update_fields=['device_user_name', 'updated_at'])

    from apps.attendance.models import AttendancePunch
    for punch in AttendancePunch.objects.filter(device=device, device_user_name=''):
        device_name = name_map.get(punch.device_user_id, '')
        if device_name:
            punch.device_user_name = device_name
            punch.save(update_fields=['device_user_name', 'updated_at'])

    return {'ok': True, 'synced': synced, 'names': name_map}


def get_device_user_name_map(device: BiometricDevice) -> dict[int, str]:
    from apps.attendance.models import BiometricDeviceUser

    return {
        u.device_user_id: u.name
        for u in BiometricDeviceUser.objects.filter(device=device, is_deleted=False).only(
            'device_user_id', 'name',
        )
        if u.name
    }


def fetch_attendance(
    device: BiometricDevice,
    *,
    clear_after: bool = False,
    force_mock: bool | None = None,
) -> tuple[list[RawAttendanceRow], str | None]:
    if is_mock_mode(force=force_mock):
        now = timezone.now()
        rows = [
            RawAttendanceRow(1, now.replace(hour=8, minute=0, second=0, microsecond=0), 'in', 1, 0, 1001),
            RawAttendanceRow(1, now.replace(hour=17, minute=0, second=0, microsecond=0), 'out', 1, 1, 1002),
            RawAttendanceRow(2, now.replace(hour=8, minute=5, second=0, microsecond=0), 'in', 1, 0, 1003),
            RawAttendanceRow(2, now.replace(hour=16, minute=55, second=0, microsecond=0), 'out', 1, 1, 1004),
        ]
        return rows, None

    ZK, ZKNetworkError, ZKErrorResponse = _import_zk()
    conn = None
    try:
        kw = _zk_connect_kwargs(device)
        zk = ZK(kw['ip'], port=kw['port'], timeout=kw['timeout'], password=kw['password'],
                force_udp=kw['force_udp'], ommit_ping=kw['ommit_ping'])
        conn = zk.connect()
        records = conn.get_attendance() or []
        rows: list[RawAttendanceRow] = []
        for rec in records:
            ts = rec.timestamp
            if timezone.is_naive(ts):
                ts = timezone.make_aware(ts, timezone.get_current_timezone())
            status = getattr(rec, 'status', None)
            punch_type, _ = punch_type_for_status(status)
            rows.append(
                RawAttendanceRow(
                    device_user_id=int(rec.user_id),
                    punched_at=ts,
                    punch_type=punch_type,
                    verify_mode=getattr(rec, 'punch', None),
                    status=status,
                    uid=getattr(rec, 'uid', None),
                )
            )
        if clear_after and rows:
            conn.clear_attendance()
        return rows, None
    except (ZKNetworkError, ZKErrorResponse, OSError, TimeoutError) as exc:
        return [], str(exc)
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def sync_device_attendance(
    device: BiometricDevice,
    *,
    clear_after: bool = False,
    force_mock: bool | None = None,
    incremental: bool = True,
) -> dict:
    from apps.attendance.models import EmployeeBiometricEnrollment
    from apps.attendance.services.punch_sync import import_raw_attendance_rows

    users_outcome = sync_device_users(device, force_mock=force_mock)
    name_map = users_outcome.get('names', {}) if users_outcome.get('ok') else get_device_user_name_map(device)

    rows, error = fetch_attendance(device, clear_after=clear_after, force_mock=force_mock)
    if error:
        device.connection_status = device.ConnectionStatus.ERROR
        device.last_error = error
        device.last_ping_at = timezone.now()
        device.save(update_fields=['connection_status', 'last_error', 'last_ping_at', 'updated_at'])
        return {'ok': False, 'error': error, 'imported': 0, 'skipped': 0}

    enroll_map = {
        e.device_user_id: e.employee_id
        for e in EmployeeBiometricEnrollment.objects.filter(device=device).only('device_user_id', 'employee_id')
    }

    outcome = import_raw_attendance_rows(
        device,
        rows,
        name_map=name_map,
        enroll_map=enroll_map,
        incremental=incremental,
    )
    imported = outcome['imported']
    skipped = outcome['skipped']
    total = len(rows)
    message = ''
    if imported == 0 and skipped > 0:
        message = 'لا سجلات جديدة — كل السجلات موجودة مسبقاً في النظام.'
    elif imported == 0 and total == 0:
        message = 'الجهاز لا يحتوي سجلات حضور حالياً.'
    return {
        'ok': True,
        'imported': imported,
        'skipped': skipped,
        'skipped_time_filter': outcome.get('skipped_time_filter', 0),
        'punches_new': outcome.get('punches_new', 0),
        'total_on_device': total,
        'batch': outcome.get('batch', ''),
        'users_synced': users_outcome.get('synced', 0),
        'message': message,
        'mock_mode': is_mock_mode(force=force_mock),
        'device_id': device.pk,
        'branch_id': device.branch_id,
    }
