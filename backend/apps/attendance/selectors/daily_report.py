"""تقرير الحضور اليومي — تجميع البصمات حسب الموظف واليوم."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.attendance.models import AttendancePunch


@dataclass(frozen=True)
class DailyAttendanceRow:
    work_date: date
    employee_id: int | None
    employee_name: str
    employee_number: str
    branch_name: str
    department_name: str
    device_name: str
    device_user_id: int
    device_user_name: str
    check_in: datetime | None
    check_out: datetime | None
    punch_count: int
    work_duration: timedelta | None
    status_label: str
    is_mapped: bool

    @property
    def sort_key(self) -> tuple:
        return (self.work_date, self.branch_name, self.employee_name or self.device_user_name)

    @property
    def duration_display(self) -> str:
        return _format_duration(self.work_duration)

    @property
    def check_in_display(self) -> str:
        return _format_time(self.check_in)

    @property
    def check_out_display(self) -> str:
        return _format_time(self.check_out)


def _format_duration(delta: timedelta | None) -> str:
    if not delta or delta.total_seconds() <= 0:
        return '—'
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f'{hours}:{minutes:02d}'


def _format_time(dt: datetime | None) -> str:
    if not dt:
        return '—'
    return timezone.localtime(dt).strftime('%H:%M')


def _pick_in_out_times(punches: list[AttendancePunch]) -> tuple[datetime | None, datetime | None]:
    ins = [p for p in punches if p.punch_type == AttendancePunch.PunchType.CHECK_IN]
    outs = [p for p in punches if p.punch_type == AttendancePunch.PunchType.CHECK_OUT]
    t_in = min((p.punched_at for p in ins), default=None)
    if t_in is None and punches:
        t_in = punches[0].punched_at
    t_out = max((p.punched_at for p in outs), default=None)
    if t_out is None and len(punches) > 1:
        t_out = punches[-1].punched_at
    if t_in and t_out and t_out < t_in:
        t_out = punches[-1].punched_at
    return t_in, t_out


def _status_label(
    *,
    punch_count: int,
    check_in: datetime | None,
    check_out: datetime | None,
    is_mapped: bool,
) -> str:
    if not is_mapped:
        return 'غير مربوط بـ HR'
    if punch_count == 0:
        return '—'
    if check_in and check_out and check_in != check_out:
        return 'مكتمل'
    if punch_count == 1:
        return 'بصمة واحدة'
    return 'غير مكتمل'


def build_daily_attendance_rows(qs: QuerySet) -> list[DailyAttendanceRow]:
    """يجمع سجلات البصمة إلى صفوف (موظف/مستخدم جهاز × يوم)."""
    groups: dict[tuple, list[AttendancePunch]] = defaultdict(list)
    for punch in qs.iterator(chunk_size=3000):
        day = timezone.localtime(punch.punched_at).date()
        emp_key = punch.employee_id if punch.employee_id else 0
        key = (day, emp_key, punch.device_id, punch.device_user_id)
        groups[key].append(punch)

    rows: list[DailyAttendanceRow] = []
    for (_, _, device_id, device_user_id), punches in groups.items():
        punches.sort(key=lambda p: p.punched_at)
        first = punches[0]
        work_date = timezone.localtime(first.punched_at).date()
        employee = first.employee
        device = first.device
        check_in, check_out = _pick_in_out_times(punches)
        duration = None
        if check_in and check_out and check_out > check_in:
            duration = check_out - check_in
        is_mapped = employee is not None
        rows.append(
            DailyAttendanceRow(
                work_date=work_date,
                employee_id=employee.pk if employee else None,
                employee_name=employee.name if employee else '—',
                employee_number=employee.employee_number if employee and employee.employee_number else '—',
                branch_name=(
                    (employee.branch.name if employee and employee.branch else None)
                    or (device.branch.name if device and device.branch else None)
                    or '—'
                ),
                department_name=(
                    employee.department.name if employee and employee.department else '—'
                ),
                device_name=device.name if device else '—',
                device_user_id=device_user_id,
                device_user_name=first.device_user_name or '—',
                check_in=check_in,
                check_out=check_out,
                punch_count=len(punches),
                work_duration=duration,
                status_label=_status_label(
                    punch_count=len(punches),
                    check_in=check_in,
                    check_out=check_out,
                    is_mapped=is_mapped,
                ),
                is_mapped=is_mapped,
            ),
        )

    rows.sort(key=lambda r: r.sort_key, reverse=True)
    return rows


def summarize_daily_rows(rows: list[DailyAttendanceRow]) -> dict:
    complete = sum(1 for r in rows if r.status_label == 'مكتمل')
    single = sum(1 for r in rows if r.status_label == 'بصمة واحدة')
    incomplete = sum(1 for r in rows if r.status_label == 'غير مكتمل')
    unmapped = sum(1 for r in rows if not r.is_mapped)
    return {
        'total_days': len(rows),
        'complete': complete,
        'single_punch': single,
        'incomplete': incomplete,
        'unmapped': unmapped,
        'mapped': len(rows) - unmapped,
    }


def daily_rows_to_table(rows: list[DailyAttendanceRow]) -> dict:
    """تحويل الصفوف لعرض التقارير العامة (columns + rows)."""
    columns = [
        'التاريخ', 'الموظف', 'الرقم الوظيفي', 'الفرع', 'القسم', 'الجهاز',
        'رقم المستخدم', 'وقت الدخول', 'وقت الخروج', 'عدد البصمات', 'مدة العمل', 'الحالة',
    ]
    table_rows = [
        [
            str(r.work_date),
            r.employee_name if r.is_mapped else r.device_user_name,
            r.employee_number,
            r.branch_name,
            r.department_name,
            r.device_name,
            str(r.device_user_id),
            _format_time(r.check_in),
            _format_time(r.check_out),
            str(r.punch_count),
            _format_duration(r.work_duration),
            r.status_label,
        ]
        for r in rows
    ]
    return {'columns': columns, 'rows': table_rows}
