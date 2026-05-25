"""استعلامات ربط الموظف بأجهزة البصمة."""
from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.attendance.models import EmployeeBiometricEnrollment


def enrollments_for_employee(employee_id: int) -> QuerySet:
    return (
        EmployeeBiometricEnrollment.objects.filter(
            employee_id=employee_id, is_deleted=False,
        )
        .select_related('device', 'device__branch')
        .order_by('device__name')
    )


def enrollment_filter_q(enrollments: list[EmployeeBiometricEnrollment]) -> Q:
    """
    بصمات مطابقة لربط الجهاز فقط (device_id + device_user_id).
    لا يعتمد على employee_id وحده لتجنب سجلات أجهزة أخرى.
    """
    if not enrollments:
        return Q(pk__in=[])
    q = Q()
    for en in enrollments:
        q |= Q(device_id=en.device_id, device_user_id=en.device_user_id)
    return q


def apply_employee_enrollment_to_filters(filters: dict, employee_id: int) -> dict:
    """عند فلترة موظف: ضبط الجهاز ورقم المستخدم من التسجيل."""
    enrollments = list(enrollments_for_employee(employee_id))
    if not enrollments:
        return {**filters, 'enrollments': enrollments}

    updated = {**filters, 'enrollments': enrollments}
    if len(enrollments) == 1:
        en = enrollments[0]
        updated['device_id'] = en.device_id
        updated['device_user_id'] = en.device_user_id
    elif len(enrollments) > 1 and not updated.get('device_id'):
        updated['device_id'] = enrollments[0].device_id
    return updated


def preferred_device_id(enrollments: list[EmployeeBiometricEnrollment]) -> int | None:
    if len(enrollments) == 1:
        return enrollments[0].device_id
    return enrollments[0].device_id if enrollments else None
