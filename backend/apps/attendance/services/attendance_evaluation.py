"""
تقييم حضور البصمة — مصدر حقيقة واحد لحساب التأخير والخروج المبكر.

التدفق: AttendancePunch → build_daily_attendance_rows (أول CHECK_IN/يوم)
        → evaluate_daily_checkin / evaluate_daily_checkout
        → إنذارات late-alerts / فلتر تبويب الموظف / تقرير Excel
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from apps.attendance.models import AttendancePunch, EmployeeBiometricSettings

DEFAULT_LATE_GRACE_MINUTES = 30

ENTRY_PUNCH_TYPES = frozenset({
    AttendancePunch.PunchType.CHECK_IN,
    AttendancePunch.PunchType.UNKNOWN,
})


@dataclass(frozen=True)
class CheckinEvaluation:
    is_late: bool
    late_minutes: int
    late_after_grace_minutes: int
    expected_check_in: time
    grace_minutes: int
    cutoff_at: datetime


@dataclass(frozen=True)
class CheckoutEvaluation:
    is_early: bool
    early_minutes: int


def grace_minutes_for(settings: EmployeeBiometricSettings | None) -> int:
    if not settings:
        return DEFAULT_LATE_GRACE_MINUTES
    return settings.late_grace_minutes or DEFAULT_LATE_GRACE_MINUTES


def checkin_cutoff(work_date: date, expected_check_in: time, grace_minutes: int) -> datetime:
    """آخر لحظة مقبولة للدخول (متوقع + سماح) في التوقيت المحلي."""
    tz = timezone.get_current_timezone()
    base = datetime.combine(work_date, expected_check_in)
    if timezone.is_naive(base):
        base = timezone.make_aware(base, tz)
    return timezone.localtime(base) + timedelta(minutes=grace_minutes)


def _expected_checkin_datetime(work_date: date, expected_check_in: time) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(work_date, expected_check_in), tz)


def evaluate_daily_checkin(
    work_date: date,
    check_in_dt: datetime | None,
    settings: EmployeeBiometricSettings | None,
) -> CheckinEvaluation | None:
    """
    تقييم تأخير الدخول لصف يومي (أول بصمة دخول في اليوم).
    يُرجع None إذا لا يوجد وقت متوقع أو بصمة دخول.
    """
    if not settings or not settings.expected_check_in or not check_in_dt:
        return None

    grace = grace_minutes_for(settings)
    expected_dt = _expected_checkin_datetime(work_date, settings.expected_check_in)
    check_in_local = timezone.localtime(check_in_dt)
    cutoff = expected_dt + timedelta(minutes=grace)
    late_total = int((check_in_local - expected_dt).total_seconds() // 60)
    late_after_grace = int((check_in_local - cutoff).total_seconds() // 60)
    is_late = check_in_local > cutoff

    return CheckinEvaluation(
        is_late=is_late,
        late_minutes=max(0, late_total),
        late_after_grace_minutes=max(0, late_after_grace) if is_late else 0,
        expected_check_in=settings.expected_check_in,
        grace_minutes=grace,
        cutoff_at=cutoff,
    )


def evaluate_daily_checkout(
    work_date: date,
    check_out_dt: datetime | None,
    settings: EmployeeBiometricSettings | None,
) -> CheckoutEvaluation | None:
    """تقييم خروج مبكر لصف يومي."""
    if not settings or not settings.expected_check_out or not check_out_dt:
        return None

    tz = timezone.get_current_timezone()
    expected_out = timezone.make_aware(
        datetime.combine(work_date, settings.expected_check_out), tz,
    )
    check_out_local = timezone.localtime(check_out_dt)
    if check_out_local >= expected_out:
        return CheckoutEvaluation(is_early=False, early_minutes=0)

    early_mins = int((expected_out - check_out_local).total_seconds() // 60)
    return CheckoutEvaluation(is_early=True, early_minutes=max(0, early_mins))


def punch_counts_as_late_entry(
    punch: AttendancePunch,
    settings: EmployeeBiometricSettings | None,
) -> bool:
    """هل تُخفى بصمة الدخول في تبويب الموظف (بعد cutoff)؟"""
    if not settings or not settings.expected_check_in:
        return False
    if punch.punch_type not in ENTRY_PUNCH_TYPES:
        return False
    local = timezone.localtime(punch.punched_at)
    cutoff = checkin_cutoff(
        local.date(),
        settings.expected_check_in,
        grace_minutes_for(settings),
    )
    return local > cutoff
