"""حذف نهائي لجهاز البصمة وكل بياناته من قاعدة البيانات."""
from __future__ import annotations

from django.db import transaction

from apps.attendance.models import (
    AttendancePunch,
    BiometricDevice,
    BiometricDeviceUser,
    EmployeeBiometricEnrollment,
)
from apps.attendance.services.agent_pull_queue import acknowledge_pull_request
from apps.attendance.services.device_primary_key import _fix_id_sequence


@transaction.atomic
def purge_biometric_device(device: BiometricDevice) -> dict[str, int]:
    """
    حذف الجهاز نهائياً مع السجلات المرتبطة (بصمات، مستخدمون، تسجيلات HR).
    يحرّر device_id لإعادة الاستخدام.
    """
    device_id = device.pk
    punch_qs = AttendancePunch.all_objects.filter(device_id=device_id)
    user_qs = BiometricDeviceUser.all_objects.filter(device_id=device_id)
    enroll_qs = EmployeeBiometricEnrollment.all_objects.filter(device_id=device_id)

    counts = {
        'punches': punch_qs.count(),
        'device_users': user_qs.count(),
        'enrollments': enroll_qs.count(),
    }

    punch_qs.hard_delete()
    user_qs.hard_delete()
    enroll_qs.hard_delete()
    device.hard_delete()
    acknowledge_pull_request(device_id)
    _fix_id_sequence()
    return counts


def purge_soft_deleted_biometric_devices() -> list[dict[str, int | str]]:
    """مسح كل الأجهزة المحذوفة منطقياً سابقاً (تنظيف لمرة واحدة)."""
    results: list[dict[str, int | str]] = []
    for device in BiometricDevice.all_objects.filter(is_deleted=True).order_by('pk'):
        device_id = device.pk
        name = device.name
        counts = purge_biometric_device(device)
        results.append({'device_id': device_id, 'name': name, **counts})
    return results
