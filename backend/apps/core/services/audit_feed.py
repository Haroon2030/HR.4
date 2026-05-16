"""
تجميع أحداث التدقيق من نماذج Historical (simple_history) + SystemAuditLog لعرض موحّد.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.urls import NoReverseMatch, reverse

from apps.core.services.audit_diff import AuditChangeLine, summarize_history_changes

HISTORY_VERB_AR = {'+': 'إنشاء', '~': 'تعديل', '-': 'حذف'}


@dataclass(frozen=True)
class AuditEvent:
    when: datetime
    source_key: str
    source_label: str
    verb_ar: str
    operation_ar: str
    actor: str
    summary: str
    details: str
    detail_lines: tuple[AuditChangeLine, ...]
    link: str


def _safe_reverse(viewname: str, **kwargs) -> str:
    try:
        return reverse(viewname, kwargs=kwargs)
    except NoReverseMatch:
        return ''


def _actor_name(history_row) -> str:
    u = getattr(history_row, 'history_user', None)
    if u is None:
        return '—'
    return (getattr(u, 'get_full_name', lambda: '')() or '').strip() or u.get_username()


def _actor_from_user(user) -> str:
    if user is None:
        return '—'
    return (user.get_full_name() or '').strip() or user.get_username()


def _history_event(
    *,
    h,
    source_key: str,
    source_label: str,
    object_summary: str,
    link: str,
) -> AuditEvent:
    verb = HISTORY_VERB_AR.get(h.history_type, h.history_type or '—')
    operation_ar, details, detail_lines = summarize_history_changes(h, entity_label=source_label)
    return AuditEvent(
        when=h.history_date,
        source_key=source_key,
        source_label=source_label,
        verb_ar=verb,
        operation_ar=operation_ar,
        actor=_actor_name(h),
        summary=object_summary,
        details=details,
        detail_lines=tuple(detail_lines),
        link=link,
    )


def _employee_events(*, branch_ids: set[int] | None, take: int) -> list[AuditEvent]:
    from apps.employees.models import Employee

    Hist = Employee.history.model
    qs = Hist.objects.select_related('history_user').order_by('-history_date')
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=list(branch_ids))
    out: list[AuditEvent] = []
    for h in qs[:take]:
        name = getattr(h, 'name', '') or '—'
        out.append(
            _history_event(
                h=h,
                source_key='employee',
                source_label='موظف',
                object_summary=f'{name} (معرّف {h.id})',
                link=_safe_reverse('web:view_employee', employee_id=h.id),
            )
        )
    return out


def _pending_action_events(*, branch_ids: set[int] | None, take: int) -> list[AuditEvent]:
    from apps.core.models import PendingAction

    Hist = PendingAction.history.model
    qs = Hist.objects.select_related('history_user', 'employee').order_by('-history_date')
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=list(branch_ids))
    out: list[AuditEvent] = []
    for h in qs[:take]:
        emp_name = getattr(h.employee, 'name', None) if getattr(h, 'employee_id', None) else '—'
        label = getattr(h, 'get_action_type_display', lambda: h.action_type)()
        out.append(
            _history_event(
                h=h,
                source_key='pending_action',
                source_label='طلب عملية',
                object_summary=f'{label} — {emp_name}',
                link=_safe_reverse('web:pending_action_detail', action_id=h.id),
            )
        )
    return out


def _payroll_run_events(*, branch_ids: set[int] | None, take: int) -> list[AuditEvent]:
    from apps.payroll.models import PayrollRun

    Hist = PayrollRun.history.model
    qs = Hist.objects.select_related('history_user', 'branch').order_by('-history_date')
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=list(branch_ids))
    out: list[AuditEvent] = []
    for h in qs[:take]:
        br = getattr(h.branch, 'name', None) if getattr(h, 'branch_id', None) else '—'
        out.append(
            _history_event(
                h=h,
                source_key='payroll_run',
                source_label='مسير رواتب',
                object_summary=f'{br} — {h.period_year}/{h.period_month:02d} ({h.get_status_display()})',
                link=_safe_reverse('web:view_payroll_run', run_id=h.id),
            )
        )
    return out


def _user_profile_events(*, branch_ids: set[int] | None, take: int) -> list[AuditEvent]:
    from apps.core.models import UserProfile

    Hist = UserProfile.history.model
    qs = Hist.objects.select_related('history_user', 'user', 'branch', 'role').order_by('-history_date')
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=list(branch_ids))
    out: list[AuditEvent] = []
    for h in qs[:take]:
        uname = getattr(h.user, 'get_username', lambda: str(h.user_id))()
        out.append(
            _history_event(
                h=h,
                source_key='user_profile',
                source_label='ملف مستخدم',
                object_summary=f'ملف مستخدم: {uname}',
                link=_safe_reverse('web:edit_user', user_id=h.user_id),
            )
        )
    return out


def _system_audit_branch_q(branch_ids: set[int]):
    from django.db.models import Q
    from apps.core.models import UserProfile

    user_ids = UserProfile.objects.filter(branch_id__in=list(branch_ids)).values_list('user_id', flat=True)
    return Q(target_user_id__in=user_ids) | Q(actor_id__in=user_ids)


def _system_audit_events(*, branch_ids: set[int] | None, take: int) -> list[AuditEvent]:
    from apps.core.models import SystemAuditLog

    qs = SystemAuditLog.objects.select_related('actor', 'target_user').order_by('-created_at')
    if branch_ids is not None:
        qs = qs.filter(_system_audit_branch_q(branch_ids))
    out: list[AuditEvent] = []
    for row in qs[:take]:
        target = row.target_user
        uname = target.get_username() if target else '—'
        sys_lines: tuple[AuditChangeLine, ...] = ()
        if row.details:
            sys_lines = (AuditChangeLine(label='التفاصيل', old='—', new=row.details),)
        out.append(
            AuditEvent(
                when=row.created_at,
                source_key='system',
                source_label='عملية نظام',
                verb_ar=row.get_action_display(),
                operation_ar=row.summary,
                actor=_actor_from_user(row.actor),
                summary=f'المستخدم: {uname}' if target else row.summary,
                details=row.details,
                detail_lines=sys_lines,
                link=_safe_reverse('web:edit_user', user_id=target.pk) if target else '',
            )
        )
    return out


def collect_audit_events(
    *,
    branch_ids: set[int] | None,
    source: str,
    limit: int = 60,
) -> list[AuditEvent]:
    """
    source: all | employee | pending_action | payroll_run | user_profile | system
    """
    source = (source or 'all').strip().lower()
    limit = max(10, min(int(limit or 60), 150))
    take_each = limit if source != 'all' else max(10, min(35, limit // 4))

    chunks: list[AuditEvent] = []

    def add(fn, key: str) -> None:
        if source not in ('all', key):
            return
        chunks.extend(fn(branch_ids=branch_ids, take=take_each))

    add(_system_audit_events, 'system')
    add(_employee_events, 'employee')
    add(_pending_action_events, 'pending_action')
    add(_payroll_run_events, 'payroll_run')
    add(_user_profile_events, 'user_profile')

    if not chunks:
        return []

    chunks.sort(key=lambda e: e.when, reverse=True)
    return chunks[:limit]
