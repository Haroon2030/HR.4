"""جمع بيانات تقرير العمليات اليومي — أقسام منظمة."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.core.models import Branch, PendingAction
from apps.employees.models import EmployeeLeave, EmploymentRequest
from apps.payroll.models import PayrollLine


@dataclass(frozen=True)
class OperationsReportRow:
    ref: str
    employee_name: str
    branch_name: str
    details: str
    amount_label: str
    status_label: str
    date_label: str
    sort_key: tuple


@dataclass(frozen=True)
class OperationsReportSection:
    key: str
    title: str
    accent_rgb: tuple[int, int, int]
    completed_rows: list[OperationsReportRow] = field(default_factory=list)
    pending_rows: list[OperationsReportRow] = field(default_factory=list)


@dataclass(frozen=True)
class OperationsReportBundle:
    report_date: date
    sections: list[OperationsReportSection]
    employment_pending: list[OperationsReportRow] = field(default_factory=list)
    employment_completed: list[OperationsReportRow] = field(default_factory=list)


SECTION_SPECS: tuple[tuple[str, str, tuple[int, int, int], tuple[str, ...]], ...] = (
    ('loans', 'السلف', (37, 99, 235), (PendingAction.ActionType.LOAN_REQUEST,)),
    ('leaves', 'الإجازات', (16, 185, 129), (PendingAction.ActionType.LEAVE,)),
    ('transfers', 'التنقلات', (99, 102, 241), (PendingAction.ActionType.TRANSFER,)),
    (
        'terminations',
        'التصفيات العادية',
        (244, 63, 94),
        (
            PendingAction.ActionType.TERMINATE,
            PendingAction.ActionType.CONTRACT_END,
            PendingAction.ActionType.END_OF_SERVICE,
        ),
    ),
    ('absences', 'الغيابات', (249, 115, 22), (PendingAction.ActionType.ABSENCE,)),
    ('additions', 'الإضافات', (14, 165, 233), ()),
    ('salary_adjustments', 'تعديلات الراتب', (217, 119, 6), (PendingAction.ActionType.SALARY_ADJUST,)),
)

_LEAVE_LABELS = dict(EmployeeLeave.LeaveType.choices)


def _fmt_dt(value) -> str:
    if not value:
        return '—'
    return timezone.localtime(value).strftime('%Y-%m-%d %H:%M')


def _money(value) -> str:
    if value in (None, ''):
        return '—'
    try:
        dec = Decimal(str(value))
    except Exception:
        return str(value)
    if dec == dec.to_integral_value():
        return f'{dec.to_integral_value():,}'
    return f'{dec:,.2f}'


def _branch_name(branch_id, cache: dict[int, str]) -> str:
    if not branch_id:
        return '—'
    if branch_id not in cache:
        cache[branch_id] = Branch.objects.filter(pk=branch_id).values_list('name', flat=True).first() or '—'
    return cache[branch_id]


def _action_details(action: PendingAction, branch_cache: dict[int, str]) -> tuple[str, str]:
    p = action.payload or {}
    action_type = action.action_type

    if action_type == PendingAction.ActionType.LEAVE:
        leave_type = _LEAVE_LABELS.get(p.get('leave_type'), p.get('leave_type', '—'))
        date_from = p.get('date_from', '—')
        date_to = p.get('date_to', '—')
        days = p.get('days')
        days_part = f' ({days} يوم)' if days else ''
        return f'{leave_type}: {date_from} → {date_to}{days_part}', '—'

    if action_type == PendingAction.ActionType.TRANSFER:
        to_branch = _branch_name(p.get('new_branch_id'), branch_cache)
        reason = (p.get('reason') or '').strip()
        details = f'نقل إلى {to_branch}'
        if reason:
            details = f'{details} — {reason[:40]}'
        return details, '—'

    if action_type == PendingAction.ActionType.LOAN_REQUEST:
        amount = _money(p.get('amount'))
        installments = p.get('installments') or '—'
        reason = (p.get('reason') or '').strip()
        details = f'{installments} قسط'
        if reason:
            details = f'{details} — {reason[:35]}'
        return details, f'{amount} ر.س'

    if action_type == PendingAction.ActionType.ABSENCE:
        absence_date = p.get('absence_date', '—')
        days = p.get('days') or 1
        return f'تاريخ {absence_date} — {days} يوم', '—'

    if action_type == PendingAction.ActionType.SALARY_ADJUST:
        new_basic = _money(p.get('new_basic_salary'))
        effective = p.get('effective_date', '—')
        reason = (p.get('reason') or '').strip()
        details = f'سريان {effective}'
        if reason:
            details = f'{details} — {reason[:35]}'
        return details, f'{new_basic} ر.س'

    if action_type in (
        PendingAction.ActionType.TERMINATE,
        PendingAction.ActionType.CONTRACT_END,
        PendingAction.ActionType.END_OF_SERVICE,
    ):
        end_date = p.get('end_date', '—')
        end_reason = (p.get('end_reason') or p.get('reason') or '').strip()
        label = action.get_action_type_display()
        details = f'{label} — {end_date}'
        if end_reason:
            details = f'{details} — {end_reason[:35]}'
        return details, '—'

    notes = (p.get('notes') or p.get('reason') or '').strip()
    return notes[:60] if notes else action.get_action_type_display(), '—'


def _action_row(action: PendingAction, *, completed: bool, branch_cache: dict[int, str]) -> OperationsReportRow:
    when = action.executed_at if completed else action.requested_at
    details, amount = _action_details(action, branch_cache)
    return OperationsReportRow(
        ref=f'PA-{action.pk}',
        employee_name=action.employee.name if action.employee_id else '—',
        branch_name=action.branch.name if action.branch_id else '—',
        details=details,
        amount_label=amount,
        status_label=action.get_status_display(),
        date_label=_fmt_dt(when),
        sort_key=(when or timezone.now(), action.pk),
    )


def _employment_row(req: EmploymentRequest, *, completed: bool) -> OperationsReportRow:
    when = req.officer_reviewed_at if completed else req.created_at
    salary = _money(req.basic_salary) if req.basic_salary else '—'
    return OperationsReportRow(
        ref=f'ER-{req.pk}',
        employee_name=req.name,
        branch_name=req.branch.name if req.branch_id else '—',
        details='طلب توظيف جديد',
        amount_label=f'{salary} ر.س' if salary != '—' else '—',
        status_label=req.get_status_display(),
        date_label=_fmt_dt(when),
        sort_key=(when or timezone.now(), req.pk),
    )


def _payroll_addition_rows(report_date: date) -> list[OperationsReportRow]:
    lines = (
        PayrollLine.objects.filter(is_deleted=False, updated_at__date=report_date)
        .filter(Q(bonus__gt=0) | Q(overtime__gt=0) | Q(other_addition__gt=0))
        .select_related('employee', 'run', 'run__branch')
        .order_by('-updated_at')
    )
    rows: list[OperationsReportRow] = []
    for line in lines:
        parts: list[str] = []
        if line.bonus and line.bonus > 0:
            parts.append(f'مكافأة {_money(line.bonus)}')
        if line.overtime and line.overtime > 0:
            parts.append(f'إضافي {_money(line.overtime)}')
        if line.other_addition and line.other_addition > 0:
            parts.append(f'أخرى {_money(line.other_addition)}')
        total = (line.bonus or 0) + (line.overtime or 0) + (line.other_addition or 0)
        period = f'{line.run.period_year}/{line.run.period_month:02d}' if line.run_id else '—'
        rows.append(
            OperationsReportRow(
                ref=f'PR-{line.pk}',
                employee_name=line.employee.name if line.employee_id else '—',
                branch_name=line.run.branch.name if line.run_id and line.run.branch_id else '—',
                details=f'مسير {period} — {" | ".join(parts)}',
                amount_label=f'{_money(total)} ر.س',
                status_label='مُسجّل',
                date_label=_fmt_dt(line.updated_at),
                sort_key=(line.updated_at or timezone.now(), line.pk),
            )
        )
    return rows


def _pending_actions_qs():
    return (
        PendingAction.objects.filter(is_deleted=False)
        .exclude(status=PendingAction.Status.APPROVED)
        .select_related('employee', 'branch')
        .order_by('-requested_at')
    )


def _completed_actions_qs(report_date: date):
    return (
        PendingAction.objects.filter(
            is_deleted=False,
            status=PendingAction.Status.APPROVED,
            executed_at__date=report_date,
        )
        .select_related('employee', 'branch')
        .order_by('-executed_at')
    )


def _pending_employment_qs():
    return (
        EmploymentRequest.objects.filter(is_deleted=False)
        .exclude(status__in=(EmploymentRequest.Status.APPROVED, EmploymentRequest.Status.REJECTED))
        .select_related('branch')
        .order_by('-created_at')
    )


def _completed_employment_qs(report_date: date):
    return (
        EmploymentRequest.objects.filter(
            is_deleted=False,
            status=EmploymentRequest.Status.APPROVED,
            officer_reviewed_at__date=report_date,
        )
        .select_related('branch')
        .order_by('-officer_reviewed_at')
    )


def collect_operations_report(
    *,
    report_date: date | None = None,
    include_pending: bool = True,
    include_completed: bool = True,
) -> OperationsReportBundle:
    report_date = report_date or timezone.localdate()
    branch_cache: dict[int, str] = {}

    sections: list[OperationsReportSection] = []
    for key, title, accent, action_types in SECTION_SPECS:
        completed_rows: list[OperationsReportRow] = []
        pending_rows: list[OperationsReportRow] = []

        if key == 'additions':
            if include_completed:
                completed_rows = _payroll_addition_rows(report_date)
        else:
            type_set = set(action_types)
            if include_completed:
                completed_rows = [
                    _action_row(a, completed=True, branch_cache=branch_cache)
                    for a in _completed_actions_qs(report_date)
                    if a.action_type in type_set
                ]
            if include_pending:
                pending_rows = [
                    _action_row(a, completed=False, branch_cache=branch_cache)
                    for a in _pending_actions_qs()
                    if a.action_type in type_set
                ]

        completed_rows.sort(key=lambda r: r.sort_key, reverse=True)
        pending_rows.sort(key=lambda r: r.sort_key, reverse=True)
        sections.append(
            OperationsReportSection(
                key=key,
                title=title,
                accent_rgb=accent,
                completed_rows=completed_rows,
                pending_rows=pending_rows,
            )
        )

    employment_pending: list[OperationsReportRow] = []
    employment_completed: list[OperationsReportRow] = []
    if include_pending:
        employment_pending = [_employment_row(r, completed=False) for r in _pending_employment_qs()]
    if include_completed:
        employment_completed = [_employment_row(r, completed=True) for r in _completed_employment_qs(report_date)]

    return OperationsReportBundle(
        report_date=report_date,
        sections=sections,
        employment_pending=employment_pending,
        employment_completed=employment_completed,
    )


def collect_operations_report_rows(
    *,
    report_date: date | None = None,
    include_pending: bool = True,
    include_completed: bool = True,
) -> tuple[list[OperationsReportRow], list[OperationsReportRow]]:
    """توافق خلفي — قائمة مسطّحة للمعلّق والمُنجز."""
    bundle = collect_operations_report(
        report_date=report_date,
        include_pending=include_pending,
        include_completed=include_completed,
    )
    pending: list[OperationsReportRow] = []
    completed: list[OperationsReportRow] = []
    for section in bundle.sections:
        pending.extend(section.pending_rows)
        completed.extend(section.completed_rows)
    pending.extend(bundle.employment_pending)
    completed.extend(bundle.employment_completed)
    pending.sort(key=lambda r: r.sort_key, reverse=True)
    completed.sort(key=lambda r: r.sort_key, reverse=True)
    return pending, completed
