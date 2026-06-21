"""إنذارات تأخير البصمة — مرتبطة بإعدادات تبويب البصمة وسحب السجلات."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.attendance.models import EmployeeBiometricSettings
from apps.attendance.selectors.biometric_devices import filter_biometric_devices_for_user
from apps.attendance.selectors.daily_report import build_daily_attendance_rows
from apps.attendance.selectors.punch_records import get_punch_queryset


@dataclass(frozen=True)
class LateCheckinAlert:
    work_date: date
    employee_id: int
    employee_name: str
    branch_name: str
    department_name: str
    expected_check_in: str
    grace_minutes: int
    check_in_time: str
    late_minutes: int
    late_after_grace_minutes: int
    note: str

    @property
    def sort_key(self) -> tuple:
        return (self.work_date, self.late_minutes, self.employee_name)


def _parse_filter_dates(filters: dict) -> tuple[date | None, date | None]:
    date_from = None
    date_to = None
    if filters.get('date_from'):
        date_from = date.fromisoformat(filters['date_from'])
    if filters.get('date_to'):
        date_to = date.fromisoformat(filters['date_to'])
    return date_from, date_to


def punches_queryset_for_late_alerts(user, filters: dict) -> QuerySet:
    from apps.attendance.selectors.employee_enrollment import (
        apply_employee_enrollment_to_filters,
        enrollment_filter_q,
    )

    date_from, date_to = _parse_filter_dates(filters)
    employee_id = filters.get('employee_id')
    employee_enrollments = []
    if employee_id:
        filters = apply_employee_enrollment_to_filters(filters, employee_id)
        employee_enrollments = filters.get('enrollments') or []
        employee_id = None

    qs = get_punch_queryset(
        device_id=filters.get('device_id'),
        branch_ids=filters.get('branch_ids'),
        employee_id=employee_id,
        device_user_id=filters.get('device_user_id'),
        date_from=date_from,
        date_to=date_to,
        punch_type=filters.get('punch_type'),
        mapped_only=True,
        search=filters.get('search') or None,
    )
    qs = qs.filter(device_id__in=filter_biometric_devices_for_user(user).values('pk'))
    if employee_enrollments:
        qs = qs.filter(enrollment_filter_q(employee_enrollments))
    return qs


def build_late_checkin_alerts(user, filters: dict) -> list[LateCheckinAlert]:
    """
    صفوف تأخير الدخول: موظف لديه وقت دخول متوقع في إعدادات البصمة
    وبصمة دخول فعلية بعد (المتوقع + سماح التأخير).
    """
    qs = punches_queryset_for_late_alerts(user, filters)
    daily_rows = build_daily_attendance_rows(qs)
    employee_ids = [r.employee_id for r in daily_rows if r.employee_id]
    settings_map = {
        s.employee_id: s
        for s in EmployeeBiometricSettings.objects.filter(
            employee_id__in=employee_ids,
            expected_check_in__isnull=False,
        )
    }

    alerts: list[LateCheckinAlert] = []
    tz = timezone.get_current_timezone()

    for row in daily_rows:
        if not row.employee_id or not row.is_mapped or not row.check_in:
            continue
        settings = settings_map.get(row.employee_id)
        if not settings or not settings.expected_check_in:
            continue

        expected_dt = timezone.make_aware(
            datetime.combine(row.work_date, settings.expected_check_in),
            tz,
        )
        check_in_local = timezone.localtime(row.check_in)
        grace = settings.late_grace_minutes or 30
        cutoff = expected_dt + timedelta(minutes=grace)
        if check_in_local <= cutoff:
            continue

        late_total = int((check_in_local - expected_dt).total_seconds() // 60)
        late_after_grace = int((check_in_local - cutoff).total_seconds() // 60)
        alerts.append(
            LateCheckinAlert(
                work_date=row.work_date,
                employee_id=row.employee_id,
                employee_name=row.employee_name,
                branch_name=row.branch_name,
                department_name=row.department_name,
                expected_check_in=settings.expected_check_in.strftime('%H:%M'),
                grace_minutes=grace,
                check_in_time=check_in_local.strftime('%H:%M'),
                late_minutes=late_total,
                late_after_grace_minutes=late_after_grace,
                note=f'تأخر {late_total} د (بعد سماح {grace} د)',
            )
        )

    alerts.sort(key=lambda a: a.sort_key, reverse=True)
    return alerts


def summarize_late_alerts(alerts: list[LateCheckinAlert]) -> dict:
    if not alerts:
        return {
            'total': 0,
            'employees': 0,
            'avg_late_minutes': 0,
            'max_late_minutes': 0,
        }
    employee_ids = {a.employee_id for a in alerts}
    late_values = [a.late_minutes for a in alerts]
    return {
        'total': len(alerts),
        'employees': len(employee_ids),
        'avg_late_minutes': round(sum(late_values) / len(late_values)),
        'max_late_minutes': max(late_values),
    }
