"""بيانات الأرشيف الموحّد — كل إجراءات الإضافة السريعة."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils import timezone


@dataclass(frozen=True)
class ArchiveExtraRow:
    row_type: str
    row_id: str
    event_date: Any
    event_time: Any
    sort_at: datetime
    badge_label: str
    badge_icon: str
    badge_class: str
    title: str
    detail: str
    executor_name: str
    status_label: str
    status_class: str
    search_text: str
    document_url: str = ''


def archive_statement_row_type(statement) -> str:
    """نوع صف الأرشيف لإفادة — يفصل تصفية نهاية خدمة عن إنهاء خدمة عام."""
    st_type = statement.statement_type
    if st_type != 'terminate':
        return st_type
    title = (statement.title or '')
    content = (statement.content or '')
    if (
        'تصفية نهاية خدمة' in title
        or 'تصفية نهاية خدمة' in content
        or 'انتهاء عقد بانتهاء مدته' in title
        or 'انتهاء عقد بانتهاء مدته' in content
        or 'المادة 74' in title
        or 'المادة 74' in content
        or 'المادة 77' in title
        or 'المادة 77' in content
        or 'المادة 80' in title
        or 'المادة 80' in content
        or 'نهاية فترة التجربة' in title
        or 'نهاية فترة التجربة' in content
        or 'انتهاء عقد' in title
        or 'انتهاء عقد' in content
    ):
        return 'end_of_service'
    return 'terminate'


def _user_label(user) -> str:
    if not user:
        return '—'
    return user.get_full_name() or user.username or '—'


def _aware_dt(value) -> datetime:
    if value is None:
        return timezone.now()
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value)
        return value
    dt = datetime.combine(value, datetime.min.time())
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def load_schedule_archive_events(employee) -> list[ArchiveExtraRow]:
    """تغييرات جدول الدوام من سجل التاريخ."""
    from apps.core.services.audit_diff import _summarize_work_schedule
    from apps.employees.models import Employee

    History = Employee.history.model
    records = list(
        History.objects.filter(id=employee.pk)
        .select_related('history_user')
        .order_by('history_date', 'history_id')
    )
    if not records:
        return []

    rows: list[ArchiveExtraRow] = []
    prev_schedule = None
    seq = 0
    for rec in records:
        current = rec.work_schedule or ''
        if prev_schedule is not None and current != prev_schedule:
            seq += 1
            summary = _summarize_work_schedule(current) if current else 'إفراغ جدول الدوام'
            summary = summary or 'تحديث جدول الدوام'
            rows.append(
                ArchiveExtraRow(
                    row_type='schedule',
                    row_id=f'schedule-{seq}',
                    event_date=rec.history_date,
                    event_time=rec.history_date,
                    sort_at=_aware_dt(rec.history_date),
                    badge_label='جدول دوام',
                    badge_icon='calendar-days',
                    badge_class='bg-slate-200 text-slate-700',
                    title='تحديث جدول الدوام',
                    detail=summary,
                    executor_name=_user_label(rec.history_user),
                    status_label='مُحدَّث',
                    status_class='bg-slate-100 text-slate-600',
                    search_text=f'جدول دوام {summary}',
                )
            )
        prev_schedule = current

    rows.reverse()
    return rows


def build_archive_extra_rows(*, employee) -> list[ArchiveExtraRow]:
    """صفوف الأرشيف من الإضافة السريعة (خارج statements_log)."""
    from apps.employees.models import (
        EmployeeAbsence,
        EmployeeCustody,
        EmployeeLeave,
        EmployeeLoan,
    )

    rows: list[ArchiveExtraRow] = []

    for lv in EmployeeLeave.objects.filter(employee_id=employee.pk).select_related('created_by'):
        detail_lines = [
            f'من {lv.date_from} إلى {lv.date_to}',
            f'{lv.days} يوم',
        ]
        if lv.notes:
            detail_lines.append(lv.notes)
        rows.append(
            ArchiveExtraRow(
                row_type='leave',
                row_id=f'leave-{lv.pk}',
                event_date=lv.date_from,
                event_time=lv.created_at,
                sort_at=_aware_dt(lv.created_at),
                badge_label='إجازة',
                badge_icon='plane',
                badge_class='bg-sky-100 text-sky-700',
                title=lv.get_leave_type_display(),
                detail='\n'.join(detail_lines),
                executor_name=_user_label(lv.created_by),
                status_label='مُسجَّلة',
                status_class='bg-sky-100 text-sky-700',
                search_text=f'إجازة {lv.get_leave_type_display()} {lv.notes}',
                document_url=lv.document.url if lv.document else '',
            )
        )

    for ln in EmployeeLoan.objects.filter(employee_id=employee.pk).select_related('created_by'):
        detail = (
            f'المبلغ: {ln.amount} ر.س\n'
            f'الخصم الشهري: {ln.monthly_deduction} ر.س\n'
            f'الأقساط: {ln.installments}\n'
            f'{ln.reason}\n{ln.notes}'.strip()
        )
        rows.append(
            ArchiveExtraRow(
                row_type='loan',
                row_id=f'loan-{ln.pk}',
                event_date=ln.issued_at,
                event_time=ln.created_at,
                sort_at=_aware_dt(ln.created_at),
                badge_label='سلفة',
                badge_icon='banknote',
                badge_class='bg-teal-100 text-teal-700',
                title=f'سلفة {ln.amount} ر.س',
                detail=detail,
                executor_name=_user_label(ln.created_by),
                status_label=ln.get_status_display(),
                status_class='bg-teal-100 text-teal-700',
                search_text=f'سلفة {ln.amount} {ln.reason}',
            )
        )

    for ab in EmployeeAbsence.objects.filter(employee_id=employee.pk).select_related('created_by'):
        detail = (
            f'التاريخ: {ab.absence_date}\n'
            f'الأيام: {ab.days}\n'
            f'الخصم: {ab.deduction_amount} ر.س\n'
            f'{ab.reason}\n{ab.notes}'.strip()
        )
        rows.append(
            ArchiveExtraRow(
                row_type='absence',
                row_id=f'absence-{ab.pk}',
                event_date=ab.absence_date,
                event_time=ab.created_at,
                sort_at=_aware_dt(ab.created_at),
                badge_label='غياب',
                badge_icon='user-x',
                badge_class='bg-orange-100 text-orange-700',
                title=f'غياب {ab.days} يوم',
                detail=detail,
                executor_name=_user_label(ab.created_by),
                status_label='مُسجَّل',
                status_class='bg-orange-100 text-orange-700',
                search_text=f'غياب {ab.absence_date} {ab.reason}',
            )
        )

    for cu in EmployeeCustody.objects.filter(employee_id=employee.pk).select_related('created_by'):
        receive_detail = (
            f'العهدة: {cu.item_name}\n'
            f'التفاصيل: {cu.item_details}\n'
            f'الكمية: {cu.quantity}\n'
            f'{cu.notes}'.strip()
        )
        rows.append(
            ArchiveExtraRow(
                row_type='custody_receive',
                row_id=f'custody-r-{cu.pk}',
                event_date=cu.received_at,
                event_time=cu.created_at,
                sort_at=_aware_dt(cu.created_at),
                badge_label='استلام عهدة',
                badge_icon='package',
                badge_class='bg-cyan-100 text-cyan-700',
                title=cu.item_name,
                detail=receive_detail,
                executor_name=_user_label(cu.created_by),
                status_label='مُستلَمة',
                status_class='bg-cyan-100 text-cyan-700',
                search_text=f'استلام عهدة {cu.item_name}',
            )
        )
        if cu.returned_at:
            clear_detail = (
                f'العهدة: {cu.item_name}\n'
                f'تاريخ الإعادة: {cu.returned_at}\n'
                f'{cu.return_notes}'.strip()
            )
            rows.append(
                ArchiveExtraRow(
                    row_type='custody_clear',
                    row_id=f'custody-c-{cu.pk}',
                    event_date=cu.returned_at,
                    event_time=cu.updated_at,
                    sort_at=_aware_dt(cu.updated_at),
                    badge_label='تصفية عهدة',
                    badge_icon='package-check',
                    badge_class='bg-cyan-100 text-cyan-800',
                    title=f'تصفية: {cu.item_name}',
                    detail=clear_detail,
                    executor_name=_user_label(cu.created_by),
                    status_label='مُصفّاة',
                    status_class='bg-emerald-100 text-emerald-700',
                    search_text=f'تصفية عهدة {cu.item_name}',
                )
            )

    rows.extend(load_schedule_archive_events(employee))
    return rows


def load_employee_archive_extras(*, employee, user) -> dict[str, Any]:
    _ = user
    return {
        'archive_extra_rows': build_archive_extra_rows(employee=employee),
    }
