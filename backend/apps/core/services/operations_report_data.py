"""جمع بيانات تقرير العمليات (معلّقة + مُنجزة)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from apps.core.models import PendingAction
from apps.employees.models import EmploymentRequest


@dataclass(frozen=True)
class OperationsReportRow:
    ref: str
    action_label: str
    employee_name: str
    branch_name: str
    status_label: str
    date_label: str
    sort_key: tuple


def _fmt_dt(value) -> str:
    if not value:
        return '—'
    local = timezone.localtime(value)
    return local.strftime('%Y-%m-%d %H:%M')


def _pending_actions_qs():
    return (
        PendingAction.objects.filter(is_deleted=False)
        .exclude(status=PendingAction.Status.APPROVED)
        .select_related('employee', 'branch', 'requested_by')
        .order_by('-requested_at')
    )


def _completed_actions_qs(report_date: date):
    return (
        PendingAction.objects.filter(
            is_deleted=False,
            status=PendingAction.Status.APPROVED,
            executed_at__date=report_date,
        )
        .select_related('employee', 'branch', 'requested_by')
        .order_by('-executed_at')
    )


def _pending_employment_qs():
    return (
        EmploymentRequest.objects.filter(is_deleted=False)
        .exclude(status__in=(
            EmploymentRequest.Status.APPROVED,
            EmploymentRequest.Status.REJECTED,
        ))
        .select_related('branch', 'requested_by')
        .order_by('-created_at')
    )


def _completed_employment_qs(report_date: date):
    return (
        EmploymentRequest.objects.filter(
            is_deleted=False,
            status=EmploymentRequest.Status.APPROVED,
            officer_reviewed_at__date=report_date,
        )
        .select_related('branch', 'requested_by')
        .order_by('-officer_reviewed_at')
    )


def _action_row(action: PendingAction, *, completed: bool) -> OperationsReportRow:
    when = action.executed_at if completed else action.requested_at
    return OperationsReportRow(
        ref=f'PA-{action.pk}',
        action_label=action.get_action_type_display(),
        employee_name=action.employee.name if action.employee_id else '—',
        branch_name=action.branch.name if action.branch_id else '—',
        status_label=action.get_status_display(),
        date_label=_fmt_dt(when),
        sort_key=(when or timezone.now(), action.pk),
    )


def _employment_row(req: EmploymentRequest, *, completed: bool) -> OperationsReportRow:
    when = req.officer_reviewed_at if completed else req.created_at
    return OperationsReportRow(
        ref=f'ER-{req.pk}',
        action_label='طلب توظيف',
        employee_name=req.name,
        branch_name=req.branch.name if req.branch_id else '—',
        status_label=req.get_status_display(),
        date_label=_fmt_dt(when),
        sort_key=(when or timezone.now(), req.pk),
    )


def collect_operations_report_rows(
    *,
    report_date: date | None = None,
    include_pending: bool = True,
    include_completed: bool = True,
) -> tuple[list[OperationsReportRow], list[OperationsReportRow]]:
    report_date = report_date or timezone.localdate()
    pending: list[OperationsReportRow] = []
    completed: list[OperationsReportRow] = []

    if include_pending:
        pending.extend(_action_row(a, completed=False) for a in _pending_actions_qs())
        pending.extend(_employment_row(r, completed=False) for r in _pending_employment_qs())
        pending.sort(key=lambda r: r.sort_key, reverse=True)

    if include_completed:
        completed.extend(_action_row(a, completed=True) for a in _completed_actions_qs(report_date))
        completed.extend(_employment_row(r, completed=True) for r in _completed_employment_qs(report_date))
        completed.sort(key=lambda r: r.sort_key, reverse=True)

    return pending, completed
