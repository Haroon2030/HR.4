"""
تجميع أحداث التدقيق من نماذج Historical (simple_history) لعرض موحّد.
لا يستبدل لوحة django-admin — يكمّلها بواجهة عربية للمدير العام / مدير الموارد.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.urls import NoReverseMatch, reverse

HISTORY_VERB_AR = {'+': 'إنشاء', '~': 'تعديل', '-': 'حذف'}


@dataclass(frozen=True)
class AuditEvent:
    when: datetime
    source_key: str
    source_label: str
    verb_ar: str
    actor: str
    summary: str
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


def _employee_events(*, branch_ids: set[int] | None, take: int) -> list[AuditEvent]:
    from apps.employees.models import Employee

    Hist = Employee.history.model
    qs = Hist.objects.select_related('history_user').order_by('-history_date')
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=list(branch_ids))
    out: list[AuditEvent] = []
    for h in qs[:take]:
        verb = HISTORY_VERB_AR.get(h.history_type, h.history_type or '—')
        name = getattr(h, 'name', '') or '—'
        out.append(
            AuditEvent(
                when=h.history_date,
                source_key='employee',
                source_label='موظف',
                verb_ar=verb,
                actor=_actor_name(h),
                summary=f'{name} (معرّف {h.id})',
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
        verb = HISTORY_VERB_AR.get(h.history_type, h.history_type or '—')
        emp_name = getattr(h.employee, 'name', None) if getattr(h, 'employee_id', None) else '—'
        label = getattr(h, 'get_action_type_display', lambda: h.action_type)()
        out.append(
            AuditEvent(
                when=h.history_date,
                source_key='pending_action',
                source_label='طلب عملية',
                verb_ar=verb,
                actor=_actor_name(h),
                summary=f'{label} — {emp_name}',
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
        verb = HISTORY_VERB_AR.get(h.history_type, h.history_type or '—')
        br = getattr(h.branch, 'name', None) if getattr(h, 'branch_id', None) else '—'
        out.append(
            AuditEvent(
                when=h.history_date,
                source_key='payroll_run',
                source_label='مسير رواتب',
                verb_ar=verb,
                actor=_actor_name(h),
                summary=f'{br} — {h.period_year}/{h.period_month:02d} ({h.get_status_display()})',
                link=_safe_reverse('web:view_payroll_run', run_id=h.id),
            )
        )
    return out


def _user_profile_events(*, branch_ids: set[int] | None, take: int) -> list[AuditEvent]:
    from apps.core.models import UserProfile

    Hist = UserProfile.history.model
    qs = Hist.objects.select_related('history_user', 'user', 'branch').order_by('-history_date')
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=list(branch_ids))
    out: list[AuditEvent] = []
    for h in qs[:take]:
        verb = HISTORY_VERB_AR.get(h.history_type, h.history_type or '—')
        uname = getattr(h.user, 'get_username', lambda: str(h.user_id))()
        out.append(
            AuditEvent(
                when=h.history_date,
                source_key='user_profile',
                source_label='مستخدم',
                verb_ar=verb,
                actor=_actor_name(h),
                summary=f'ملف مستخدم: {uname}',
                link=_safe_reverse('web:edit_user', user_id=h.user_id),
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
    source: all | employee | pending_action | payroll_run | user_profile
    branch_ids: None = كل الفروع (مدير عام)، وإلا تصفية على هذه الفروع.
    """
    source = (source or 'all').strip().lower()
    limit = max(10, min(int(limit or 60), 150))
    take_each = limit if source != 'all' else max(10, min(40, limit // 3))

    chunks: list[AuditEvent] = []

    def add(fn, key: str) -> None:
        if source not in ('all', key):
            return
        chunks.extend(fn(branch_ids=branch_ids, take=take_each))

    add(_employee_events, 'employee')
    add(_pending_action_events, 'pending_action')
    add(_payroll_run_events, 'payroll_run')
    add(_user_profile_events, 'user_profile')

    if not chunks:
        return []

    chunks.sort(key=lambda e: e.when, reverse=True)
    return chunks[:limit]
