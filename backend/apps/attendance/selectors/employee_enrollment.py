"""استعلامات ربط الموظف بأجهزة البصمة."""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Exists, OuterRef, Q, QuerySet

from apps.attendance.models import AttendancePunch, EmployeeBiometricEnrollment
from apps.employees.models import Employee


@dataclass(frozen=True)
class InferredBiometricLink:
    """ربط مستنتج من سجلات البصمة عند غياب EmployeeBiometricEnrollment."""

    device: object
    device_id: int
    device_user_id: int
    device_user_name: str


def enrollments_for_employee(employee_id: int) -> QuerySet:
    return (
        EmployeeBiometricEnrollment.objects.filter(
            employee_id=employee_id, is_deleted=False,
        )
        .select_related('device', 'device__branch')
        .order_by('device__name')
    )


def inferred_links_from_punches(employee: Employee) -> list[InferredBiometricLink]:
    """أزواج (جهاز، مستخدم) من بصمات مربوطة بالموظف مباشرة — احتياط عند غياب التسجيل."""
    seen: set[tuple[int, int]] = set()
    links: list[InferredBiometricLink] = []
    qs = (
        AttendancePunch.objects.filter(
            employee_id=employee.id,
            is_deleted=False,
        )
        .select_related('device', 'device__branch')
        .order_by('device__name', 'device_user_id', '-punched_at')
    )
    for punch in qs:
        key = (punch.device_id, punch.device_user_id)
        if key in seen:
            continue
        seen.add(key)
        links.append(
            InferredBiometricLink(
                device=punch.device,
                device_id=punch.device_id,
                device_user_id=punch.device_user_id,
                device_user_name=punch.device_user_name or '',
            )
        )
    return links


def effective_biometric_links(employee: Employee) -> tuple[list, bool]:
    """
    روابط العرض للموظف: تسجيلات HR أو — احتياطاً — من employee_id على البصمات.
    القيمة الثانية: True إذا وُجد تسجيل رسمي (EmployeeBiometricEnrollment).
    """
    enrollments = list(enrollments_for_employee(employee.id))
    if enrollments:
        return enrollments, True
    inferred = inferred_links_from_punches(employee)
    return inferred, False


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


def _active_enrollment_exists():
    return EmployeeBiometricEnrollment.objects.filter(
        device_id=OuterRef('device_id'),
        device_user_id=OuterRef('device_user_id'),
        is_deleted=False,
    )


def linked_punches_q() -> Q:
    """بصمة مربوطة: employee_id معيّن أو يوجد enrollment نشط لنفس الجهاز/المستخدم."""
    return Q(employee_id__isnull=False) | Q(Exists(_active_enrollment_exists()))


def unlinked_punches_q() -> Q:
    """بصمة غير مربوطة بـ HR."""
    return Q(employee_id__isnull=True) & ~Q(Exists(_active_enrollment_exists()))


def load_enrollment_employee_map(device_ids: set[int] | list[int] | None = None) -> dict[tuple[int, int], object]:
    """(device_id, device_user_id) → Employee من جدول الربط."""
    qs = EmployeeBiometricEnrollment.objects.filter(is_deleted=False).select_related(
        'employee', 'employee__branch', 'employee__department', 'employee__administration',
    )
    if device_ids:
        qs = qs.filter(device_id__in=device_ids)
    return {
        (en.device_id, en.device_user_id): en.employee
        for en in qs
        if en.employee_id
    }
