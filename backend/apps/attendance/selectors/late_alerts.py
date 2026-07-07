"""إنذارات تأخير البصمة — مرتبطة بإعدادات تبويب البصمة وسحب السجلات."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import QuerySet
from django.utils import timezone

from apps.attendance.models import EmployeeBiometricSettings
from apps.attendance.selectors.biometric_devices import filter_biometric_devices_for_user
from apps.attendance.selectors.daily_report import build_daily_attendance_result
from apps.attendance.selectors.punch_records import get_punch_queryset
from apps.attendance.services.attendance_evaluation import evaluate_daily_checkin


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


@dataclass(frozen=True)
class LateCheckinAlertsResult:
    alerts: list[LateCheckinAlert]
    truncated: bool


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


def build_late_checkin_alerts(user, filters: dict) -> LateCheckinAlertsResult:
    """
    صفوف تأخير الدخول: موظف لديه وقت دخول متوقع في إعدادات البصمة
    وبصمة دخول فعلية بعد (المتوقع + سماح التأخير).
    """
    qs = punches_queryset_for_late_alerts(user, filters)
    build_result = build_daily_attendance_result(qs)
    daily_rows = build_result.rows
    employee_ids = [r.employee_id for r in daily_rows if r.employee_id]
    settings_map = {
        s.employee_id: s
        for s in EmployeeBiometricSettings.objects.filter(
            employee_id__in=employee_ids,
            expected_check_in__isnull=False,
        )
    }

    alerts: list[LateCheckinAlert] = []

    for row in daily_rows:
        if not row.employee_id or not row.is_mapped or not row.check_in:
            continue
        settings = settings_map.get(row.employee_id)
        evaluation = evaluate_daily_checkin(row.work_date, row.check_in, settings)
        if not evaluation or not evaluation.is_late:
            continue

        check_in_local = timezone.localtime(row.check_in)
        alerts.append(
            LateCheckinAlert(
                work_date=row.work_date,
                employee_id=row.employee_id,
                employee_name=row.employee_name,
                branch_name=row.branch_name,
                department_name=row.department_name,
                expected_check_in=evaluation.expected_check_in.strftime('%H:%M'),
                grace_minutes=evaluation.grace_minutes,
                check_in_time=check_in_local.strftime('%H:%M'),
                late_minutes=evaluation.late_minutes,
                late_after_grace_minutes=evaluation.late_after_grace_minutes,
                note=f'تأخر {evaluation.late_minutes} د (بعد سماح {evaluation.grace_minutes} د)',
            )
        )

    alerts.sort(key=lambda a: a.sort_key, reverse=True)
    return LateCheckinAlertsResult(alerts=alerts, truncated=build_result.truncated)


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
