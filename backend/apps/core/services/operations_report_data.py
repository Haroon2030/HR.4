"""جمع بيانات تقرير العمليات اليومي — أقسام منظمة."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.core.models import Branch, PendingAction
from apps.core.services.operations_report_profiles import RoleReportProfile, get_role_report_profile
from apps.employees.models import Employee, EmployeeLeave, EmploymentRequest
from apps.setup.models import Administration


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
    report_title: str = 'تقرير العمليات اليومي'
    role_key: str = ''


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
    ('additions', 'إضافة موظفين جدد', (14, 165, 233), ()),
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

    if action_type == PendingAction.ActionType.CASH_SHORTAGE:
        shortage_date = p.get('shortage_date', '—')
        amount = _money(p.get('amount'))
        return f'تاريخ {shortage_date}', f'{amount} ر.س'

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


def _new_employee_row(employee: Employee) -> OperationsReportRow:
    when = employee.created_at
    emp_no = (employee.employee_number or '').strip() or '—'
    hire = employee.hire_date.isoformat() if employee.hire_date else '—'
    profession = employee.profession.name if employee.profession_id else '—'
    salary = _money(employee.total_salary) if employee.total_salary else '—'
    details = f'رقم {emp_no} — مباشرة {hire} — {profession}'
    return OperationsReportRow(
        ref=f'EM-{employee.pk}',
        employee_name=employee.name,
        branch_name=employee.branch.name if employee.branch_id else '—',
        details=details,
        amount_label=f'{salary} ر.س' if salary != '—' else '—',
        status_label=employee.get_status_display(),
        date_label=_fmt_dt(when),
        sort_key=(when or timezone.now(), employee.pk),
    )


def _administration_role(administration) -> str:
    if not administration:
        return ''
    return (getattr(administration, 'report_recipient_role', None) or '').strip()


def _employee_matches_scope(employee, profile: RoleReportProfile) -> bool:
    if not profile.scoped:
        return True
    if not employee or not employee.administration_id:
        return False
    admin = getattr(employee, 'administration', None)
    if admin is not None:
        return _administration_role(admin) == profile.role_key
    return Administration.objects.filter(
        pk=employee.administration_id,
        report_recipient_role=profile.role_key,
    ).exists()


def _administration_id_matches_scope(administration_id, profile: RoleReportProfile) -> bool:
    if not profile.scoped:
        return True
    if not administration_id:
        return False
    return Administration.objects.filter(
        pk=administration_id,
        report_recipient_role=profile.role_key,
    ).exists()


def _action_matches_scope(action: PendingAction, profile: RoleReportProfile) -> bool:
    if not profile.scoped:
        return True
    if action.employee_id and _employee_matches_scope(action.employee, profile):
        return True
    if action.administration_id:
        admin = getattr(action, 'administration', None)
        if admin is not None:
            return _administration_role(admin) == profile.role_key
        return _administration_id_matches_scope(action.administration_id, profile)
    return False


def _employment_matches_scope(req: EmploymentRequest, profile: RoleReportProfile) -> bool:
    if not profile.scoped:
        return True
    if not req.administration_id:
        return False
    admin = getattr(req, 'administration', None)
    if admin is not None:
        return _administration_role(admin) == profile.role_key
    return _administration_id_matches_scope(req.administration_id, profile)


def _new_employee_rows(report_date: date, profile: RoleReportProfile) -> list[OperationsReportRow]:
    employees = (
        Employee.objects.filter(is_deleted=False, created_at__date=report_date)
        .select_related('branch', 'profession', 'administration')
        .order_by('-created_at')
    )
    if profile.scoped:
        employees = employees.filter(administration__report_recipient_role=profile.role_key)
    return [_new_employee_row(emp) for emp in employees]


def _pending_actions_qs():
    return (
        PendingAction.objects.filter(is_deleted=False)
        .exclude(status=PendingAction.Status.APPROVED)
        .select_related('employee__administration', 'administration', 'branch')
        .order_by('-requested_at')
    )


def _completed_actions_qs(report_date: date):
    return (
        PendingAction.objects.filter(
            is_deleted=False,
            status=PendingAction.Status.APPROVED,
            executed_at__date=report_date,
        )
        .select_related('employee__administration', 'administration', 'branch')
        .order_by('-executed_at')
    )


def _pending_employment_qs(profile: RoleReportProfile):
    qs = (
        EmploymentRequest.objects.filter(is_deleted=False)
        .exclude(status__in=(EmploymentRequest.Status.APPROVED, EmploymentRequest.Status.REJECTED))
        .select_related('branch', 'administration')
        .order_by('-created_at')
    )
    if profile.scoped:
        qs = qs.filter(administration__report_recipient_role=profile.role_key)
    return qs


def bundle_has_content(
    bundle: OperationsReportBundle,
    *,
    include_pending: bool = True,
    include_completed: bool = True,
) -> bool:
    for section in bundle.sections:
        if include_completed and section.completed_rows:
            return True
        if include_pending and section.pending_rows:
            return True
    return False


def collect_operations_report(
    *,
    report_date: date | None = None,
    include_pending: bool = True,
    include_completed: bool = True,
    role_key: str | None = None,
) -> OperationsReportBundle:
    report_date = report_date or timezone.localdate()
    profile = get_role_report_profile(role_key)
    branch_cache: dict[int, str] = {}

    sections: list[OperationsReportSection] = []
    for key, title, accent, action_types in SECTION_SPECS:
        if key not in profile.section_keys:
            continue

        completed_rows: list[OperationsReportRow] = []
        pending_rows: list[OperationsReportRow] = []

        if key == 'additions':
            if include_completed:
                completed_rows = _new_employee_rows(report_date, profile)
            if include_pending:
                pending_rows = [
                    _employment_row(r, completed=False) for r in _pending_employment_qs(profile)
                ]
        else:
            type_set = set(action_types)
            if include_completed:
                completed_rows = [
                    _action_row(a, completed=True, branch_cache=branch_cache)
                    for a in _completed_actions_qs(report_date)
                    if a.action_type in type_set and _action_matches_scope(a, profile)
                ]
            if include_pending:
                pending_rows = [
                    _action_row(a, completed=False, branch_cache=branch_cache)
                    for a in _pending_actions_qs()
                    if a.action_type in type_set and _action_matches_scope(a, profile)
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

    return OperationsReportBundle(
        report_date=report_date,
        sections=sections,
        report_title=profile.title,
        role_key=profile.role_key,
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
    pending.sort(key=lambda r: r.sort_key, reverse=True)
    completed.sort(key=lambda r: r.sort_key, reverse=True)
    return pending, completed
