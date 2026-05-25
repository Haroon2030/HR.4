"""عرض بصمات موظف واحد مع فلترة وقت الدخول والتأخير."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.attendance.models import AttendancePunch, EmployeeBiometricSettings
from apps.attendance.selectors.employee_enrollment import (
    enrollment_filter_q,
    enrollments_for_employee,
)
from apps.attendance.selectors.punch_records import PUNCH_LIST_ORDERING
from apps.employees.models import Employee


def get_or_create_biometric_settings(employee: Employee) -> EmployeeBiometricSettings:
    settings, _ = EmployeeBiometricSettings.objects.get_or_create(employee=employee)
    return settings


def employee_enrollments(employee: Employee) -> QuerySet:
    return enrollments_for_employee(employee.id)


def employee_is_biometric_linked(employee: Employee) -> bool:
    return employee_enrollments(employee).exists()


def base_punches_queryset(
    employee: Employee,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet:
    """بصمات الموظف من أجهزة التسجيل فقط (جهاز + رقم مستخدم على الجهاز)."""
    enrollments = list(employee_enrollments(employee))
    if not enrollments:
        return AttendancePunch.objects.none()

    qs = (
        AttendancePunch.objects.filter(is_deleted=False)
        .filter(enrollment_filter_q(enrollments))
        .select_related('device', 'device__branch')
        .order_by(*PUNCH_LIST_ORDERING)
    )
    if date_from:
        start = timezone.make_aware(datetime.combine(date_from, time.min))
        qs = qs.filter(punched_at__gte=start)
    if date_to:
        end = timezone.make_aware(datetime.combine(date_to, time.max))
        qs = qs.filter(punched_at__lte=end)
    return qs


def _local_cutoff_for_day(day: date, check_in: time, grace_minutes: int) -> datetime:
    tz = timezone.get_current_timezone()
    base = datetime.combine(day, check_in)
    if timezone.is_naive(base):
        base = timezone.make_aware(base, tz)
    return timezone.localtime(base) + timedelta(minutes=grace_minutes)


def apply_late_checkin_filter(
    punches: list[AttendancePunch],
    settings: EmployeeBiometricSettings | None,
) -> tuple[list[AttendancePunch], int]:
    """
    إخفاء بصمات الدخول بعد (وقت الدخول + نصف ساعة افتراضياً).
    بصمات الخروج والاستراحة تبقى ظاهرة.
    """
    if not settings or not settings.expected_check_in:
        return punches, 0

    grace = settings.late_grace_minutes or 30
    hidden = 0
    visible: list[AttendancePunch] = []
    entry_types = {
        AttendancePunch.PunchType.CHECK_IN,
        AttendancePunch.PunchType.UNKNOWN,
    }

    for punch in punches:
        local = timezone.localtime(punch.punched_at)
        cutoff = _local_cutoff_for_day(local.date(), settings.expected_check_in, grace)
        if punch.punch_type in entry_types and local > cutoff:
            hidden += 1
            continue
        visible.append(punch)

    return visible, hidden


def get_employee_punch_display(
    employee: Employee,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    settings: EmployeeBiometricSettings | None = None,
) -> dict:
    settings = settings or get_or_create_biometric_settings(employee)
    enrollments = list(employee_enrollments(employee))
    linked = bool(enrollments)

    raw_qs = base_punches_queryset(employee, date_from=date_from, date_to=date_to)
    raw_list = list(raw_qs[:500])
    punches, hidden_late = apply_late_checkin_filter(raw_list, settings)
    last_punch = punches[0] if punches else None

    return {
        'linked': linked,
        'enrollments': enrollments,
        'punches': punches,
        'last_punch': last_punch,
        'hidden_late_count': hidden_late,
        'total_raw_count': len(raw_list),
        'settings': settings,
    }
