"""Arabic WhatsApp message templates for executed HR actions."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.core.models import PendingAction


def _fmt_date(value) -> str:
    if not value:
        return '—'
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return str(value)


def _fmt_money(value) -> str:
    if value is None or value == '':
        return '—'
    try:
        return f'{Decimal(str(value)):,.2f}'
    except Exception:
        return str(value)


def build_system_link(path: str) -> str:
    """رابط مطلق للنظام — من CSRF_TRUSTED_ORIGINS أو ALLOWED_HOSTS."""
    path = path if path.startswith('/') else f'/{path}'
    origins = list(getattr(settings, 'CSRF_TRUSTED_ORIGINS', None) or [])
    if origins:
        return f'{origins[0].rstrip("/")}{path}'
    hosts = [h for h in (getattr(settings, 'ALLOWED_HOSTS', None) or []) if h and h != '*']
    host = hosts[0] if hosts else 'localhost'
    port = str(getattr(settings, 'PORT', '') or '').strip()
    use_https = getattr(settings, 'USE_HTTPS', False)
    if not use_https:
        csrf = origins[0] if origins else ''
        use_https = csrf.lower().startswith('https://')
    scheme = 'https' if use_https else 'http'
    if port and port not in ('80', '443') and ':' not in host:
        return f'{scheme}://{host}:{port}{path}'
    return f'{scheme}://{host}{path}'


def _requester_name(user) -> str:
    if not user:
        return '—'
    return (user.get_full_name() or getattr(user, 'username', '') or '—').strip()


def _branch_label(obj) -> str:
    branch = getattr(obj, 'branch', None)
    if branch and getattr(branch, 'name', None):
        return branch.name
    employee = getattr(obj, 'employee', None)
    if employee and getattr(employee, 'branch', None):
        return employee.branch.name
    return '—'


def _pending_action_link(action: PendingAction) -> str:
    try:
        return build_system_link(reverse('web:pending_action_detail', kwargs={'action_id': action.pk}))
    except NoReverseMatch:
        return build_system_link('/pending-actions/')


def _employment_request_link() -> str:
    try:
        return build_system_link(reverse('web:list_employment_requests'))
    except NoReverseMatch:
        return build_system_link('/employment-requests/')


def _pending_action_summary(action: PendingAction) -> list[str]:
    lines = [
        f'📋 *{action.get_action_type_display()}*',
        f'👤 الموظف: {action.employee.name if action.employee_id else "—"}',
        f'🏢 الفرع: {_branch_label(action)}',
        f'✍️ مقدّم الطلب: {_requester_name(action.requested_by)}',
    ]
    if action.action_type == PendingAction.ActionType.CASH_SHORTAGE:
        payload = action.payload or {}
        lines.append(f'💵 المبلغ: {_fmt_money(payload.get("amount"))} ر.س')
        if action.attachment:
            lines.append('📎 تم إرفاق مستند العجز — يرجى الدخول للنظام للاعتماد.')
    return lines


def build_workflow_created_broadcast_message(obj) -> str:
    """رسالة لمدير النظام ومدير الموارد عند رفع طلب جديد."""
    from apps.employees.models import EmploymentRequest

    if isinstance(obj, EmploymentRequest):
        lines = [
            '🔔 *طلب جديد في نظام الموارد البشرية*',
            f'📋 طلب توظيف: *{obj.name}*',
            f'🏢 الفرع: {_branch_label(obj)}',
            f'✍️ مقدّم الطلب: {_requester_name(obj.requested_by)}',
            '',
            f'🔗 {_employment_request_link()}',
        ]
    else:
        lines = [
            '🔔 *طلب جديد في نظام الموارد البشرية*',
            *_pending_action_summary(obj),
            '',
            f'🔗 {_pending_action_link(obj)}',
        ]
    lines.append('')
    lines.append('— نظام الموارد البشرية')
    return '\n'.join(lines)


def build_workflow_first_stage_message(obj, *, title: str = '', message: str = '') -> str:
    """رسالة للمعتمد الأول (مدير فرع/إدارة أو محاسب)."""
    from apps.employees.models import EmploymentRequest

    header = title or 'طلب بانتظار موافقتك'
    lines = [f'📥 *{header}*']
    if message:
        lines.append(message)

    if isinstance(obj, EmploymentRequest):
        lines.extend([
            f'📋 طلب توظيف: *{obj.name}*',
            f'🏢 الفرع: {_branch_label(obj)}',
            '',
            f'🔗 {_employment_request_link()}',
        ])
    else:
        lines.extend(_pending_action_summary(obj))
        lines.extend(['', f'🔗 {_pending_action_link(obj)}'])

    lines.append('')
    lines.append('— نظام الموارد البشرية')
    return '\n'.join(lines)


def build_workflow_pending_gm_message(obj) -> str:
    """رسالة لمدير الموارد بعد موافقة المرحلة الأولى."""
    from apps.employees.models import EmploymentRequest

    if isinstance(obj, EmploymentRequest):
        lines = [
            '⏳ *طلب يحتاج تعميدك — مدير الموارد*',
            f'📋 طلب توظيف: *{obj.name}*',
            f'🏢 الفرع: {_branch_label(obj)}',
            '',
            f'🔗 {_employment_request_link()}',
        ]
    else:
        lines = [
            '⏳ *طلب يحتاج تعميدك — مدير الموارد*',
            *_pending_action_summary(obj),
            '',
            f'🔗 {_pending_action_link(obj)}',
        ]
    lines.append('')
    lines.append('— نظام الموارد البشرية')
    return '\n'.join(lines)


def build_workflow_officer_assigned_message(obj, officer) -> str:
    """رسالة للأخصائي عند إسناد طلب."""
    from apps.employees.models import EmploymentRequest

    officer_name = _requester_name(officer)
    if isinstance(obj, EmploymentRequest):
        lines = [
            f'📌 *تم إسناد طلب إليك — {officer_name}*',
            f'📋 طلب توظيف: *{obj.name}*',
            f'🏢 الفرع: {_branch_label(obj)}',
            '',
            f'🔗 {_employment_request_link()}',
        ]
    else:
        lines = [
            f'📌 *تم إسناد طلب إليك — {officer_name}*',
            *_pending_action_summary(obj),
            '',
            f'🔗 {_pending_action_link(obj)}',
        ]
    lines.append('')
    lines.append('— نظام الموارد البشرية')
    return '\n'.join(lines)


def build_executed_message(action: PendingAction, execution_message: str = '') -> str:
    """Build employee-facing message after PendingAction execution."""
    employee = action.employee
    name = employee.name or 'الموظف'
    action_label = action.get_action_type_display()
    payload = action.payload or {}

    lines = [
        f'مرحباً {name}،',
        f'تم تنفيذ عملية: *{action_label}* في نظام الموارد البشرية.',
    ]

    if action.action_type == PendingAction.ActionType.ABSENCE:
        lines.extend([
            f'📅 التاريخ: {_fmt_date(payload.get("absence_date"))}',
            f'📆 عدد الأيام: {payload.get("days") or 1}',
        ])
        if execution_message:
            lines.append(execution_message)

    elif action.action_type == PendingAction.ActionType.LEAVE:
        lines.extend([
            f'📅 من: {_fmt_date(payload.get("start_date"))}',
            f'📅 إلى: {_fmt_date(payload.get("end_date"))}',
        ])

    elif action.action_type == PendingAction.ActionType.TRANSFER:
        lines.append(f'🏢 {payload.get("destination_label") or payload.get("notes") or ""}'.strip())

    elif action.action_type == PendingAction.ActionType.SALARY_ADJUST:
        lines.append(f'💰 {payload.get("adjustment_label") or execution_message or ""}'.strip())

    elif action.action_type == PendingAction.ActionType.CASH_SHORTAGE:
        lines.extend([
            f'💵 المبلغ: {_fmt_money(payload.get("amount"))} ر.س',
            f'📅 التاريخ: {_fmt_date(payload.get("shortage_date"))}',
        ])

    elif action.action_type == PendingAction.ActionType.LOAN_REQUEST:
        lines.append(f'💰 مبلغ السلفة: {_fmt_money(payload.get("amount"))} ر.س')

    elif execution_message:
        lines.append(execution_message)

    lines.append('')
    lines.append('— نظام الموارد البشرية')
    return '\n'.join(line for line in lines if line is not None)
