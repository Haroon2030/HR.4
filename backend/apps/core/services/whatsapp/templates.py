"""Arabic WhatsApp message templates for executed HR actions."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

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
