"""تعيين أو تغيير المفتاح الأساسي لجهاز البصمة (للمطابقة مع devices.list في الوكيل)."""
from __future__ import annotations

from django.db import connection, transaction
from django.utils import timezone

from apps.attendance.models import (
    AttendancePunch,
    BiometricDevice,
    BiometricDeviceUser,
    EmployeeBiometricEnrollment,
)


def parse_requested_device_id(raw: str | None) -> int | None:
    value = (raw or '').strip()
    if not value:
        return None
    if not value.isdigit():
        raise ValueError('رقم الجهاز يجب أن يكون عدداً صحيحاً موجباً.')
    device_id = int(value)
    if device_id < 1:
        raise ValueError('رقم الجهاز يجب أن يكون 1 أو أكبر.')
    return device_id


def device_id_taken(device_id: int, *, exclude_pk: int | None = None) -> bool:
    """رقم محجوز لجهاز نشط (غير محذوف)."""
    qs = BiometricDevice.objects.filter(pk=device_id)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def _hard_clear_soft_deleted_slot(device_id: int) -> None:
    """إزالة صف محذوف منطقياً لتحرير المعرف قبل إدراج جديد."""
    stale = BiometricDevice.all_objects.filter(pk=device_id, is_deleted=True).first()
    if stale is not None:
        stale.hard_delete()


def _apply_device_fields(*, target: BiometricDevice, source: BiometricDevice) -> None:
    target.name = source.name
    target.device_type = source.device_type
    target.ip_address = source.ip_address
    target.port = source.port
    target.comm_key = source.comm_key
    target.branch_id = source.branch_id
    target.serial_number = source.serial_number
    target.firmware_version = source.firmware_version
    target.is_active = source.is_active
    target.connection_status = source.connection_status
    target.last_sync_at = source.last_sync_at
    target.last_ping_at = source.last_ping_at
    target.last_error = source.last_error
    target.notes = source.notes


def _copy_device_fields(*, source: BiometricDevice, target_pk: int) -> BiometricDevice:
    return BiometricDevice(
        pk=target_pk,
        name=source.name,
        device_type=source.device_type,
        ip_address=source.ip_address,
        port=source.port,
        comm_key=source.comm_key,
        branch_id=source.branch_id,
        serial_number=source.serial_number,
        firmware_version=source.firmware_version,
        is_active=source.is_active,
        connection_status=source.connection_status,
        last_sync_at=source.last_sync_at,
        last_ping_at=source.last_ping_at,
        last_error=source.last_error,
        notes=source.notes,
        created_at=source.created_at,
        updated_at=source.updated_at,
        is_deleted=source.is_deleted,
        deleted_at=source.deleted_at,
    )


def _repoint_device_foreign_keys(*, old_id: int, new_id: int) -> None:
    AttendancePunch.all_objects.filter(device_id=old_id).update(device_id=new_id)
    EmployeeBiometricEnrollment.all_objects.filter(device_id=old_id).update(device_id=new_id)
    BiometricDeviceUser.all_objects.filter(device_id=old_id).update(device_id=new_id)


def _fix_id_sequence() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('attendance_biometricdevice', 'id'),
                COALESCE((SELECT MAX(id) FROM attendance_biometricdevice), 1),
                true
            )
            """
        )


@transaction.atomic
def reassign_biometric_device_id(device: BiometricDevice, new_id: int) -> BiometricDevice:
    """نقل الجهاز إلى رقم جديد مع كل السجلات المرتبطة."""
    if device.pk == new_id:
        return device
    if device_id_taken(new_id, exclude_pk=device.pk):
        raise ValueError(f'رقم الجهاز {new_id} مستخدم مسبقاً.')
    _hard_clear_soft_deleted_slot(new_id)

    old_id = device.pk
    replacement = _copy_device_fields(source=device, target_pk=new_id)
    replacement.save(force_insert=True)
    _repoint_device_foreign_keys(old_id=old_id, new_id=new_id)
    device.hard_delete()
    _fix_id_sequence()
    return replacement


def create_biometric_device_with_id(device: BiometricDevice, device_id: int) -> BiometricDevice:
    """إنشاء جهاز برقم محدد (مطابقة وكيل الفرع). يعيد تفعيل الرقم إن كان محذوفاً منطقياً."""
    if device_id_taken(device_id):
        raise ValueError(f'رقم الجهاز {device_id} مستخدم مسبقاً.')

    existing = BiometricDevice.all_objects.filter(pk=device_id).first()
    if existing is not None:
        if not existing.is_deleted:
            raise ValueError(f'رقم الجهاز {device_id} مستخدم مسبقاً.')
        _apply_device_fields(target=existing, source=device)
        existing.is_deleted = False
        existing.deleted_at = None
        existing.updated_at = timezone.now()
        existing.save()
        _fix_id_sequence()
        return existing

    device.pk = device_id
    device.save(force_insert=True)
    _fix_id_sequence()
    return device
