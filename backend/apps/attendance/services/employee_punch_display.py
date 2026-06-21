"""عرض بصمات موظف واحد مع فلترة وقت الدخول والتأخير."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.attendance.models import AttendancePunch, EmployeeBiometricSettings
from apps.attendance.selectors.employee_enrollment import (
    effective_biometric_links,
    enrollment_filter_q,
    enrollments_for_employee,
)
from apps.attendance.selectors.punch_records import PUNCH_LIST_ORDERING
from apps.employees.models import Employee

# حد أمان للعرض في تبويب الموظف — الفترة الزمنية تُضيّق النتائج عادةً
MAX_EMPLOYEE_PUNCHES_DISPLAY = 5000
MAX_EMPLOYEE_PUNCHES_DEFAULT = 500


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
    """بصمات الموظف — عبر التسجيل الرسمي أو employee_id على السجل."""
    enrollments = list(employee_enrollments(employee))
    qs = AttendancePunch.objects.filter(is_deleted=False).select_related(
        'device', 'device__branch',
    )
    if enrollments:
        qs = qs.filter(enrollment_filter_q(enrollments))
    else:
        qs = qs.filter(employee_id=employee.id)

    qs = qs.order_by(*PUNCH_LIST_ORDERING)
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
    max_display: int | None = None,
) -> dict:
    settings = settings or get_or_create_biometric_settings(employee)
    enrollments, has_formal_enrollment = effective_biometric_links(employee)
    linked = bool(enrollments)

    cap = max_display if max_display is not None else MAX_EMPLOYEE_PUNCHES_DEFAULT
    cap = min(max(cap, 1), MAX_EMPLOYEE_PUNCHES_DISPLAY)

    raw_qs = base_punches_queryset(employee, date_from=date_from, date_to=date_to)
    total_raw_count = raw_qs.count()
    raw_list = list(raw_qs[:cap])
    truncated = total_raw_count > len(raw_list)
    punches, hidden_late = apply_late_checkin_filter(raw_list, settings)
    last_punch = punches[0] if punches else None

    return {
        'linked': linked,
        'has_formal_enrollment': has_formal_enrollment,
        'enrollments': enrollments,
        'punches': punches,
        'last_punch': last_punch,
        'hidden_late_count': hidden_late,
        'total_raw_count': total_raw_count,
        'displayed_count': len(punches),
        'truncated': truncated,
        'settings': settings,
    }
