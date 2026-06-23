"""إشعارات واتساب لمراحل دورة الموافقات."""
from __future__ import annotations

import logging

from apps.core.models import PendingAction, WhatsAppMessageLog
from apps.core.services.whatsapp import dispatcher, templates
from apps.setup.models import WorkflowWhatsAppSettings

logger = logging.getLogger(__name__)

_ROLE_KEY_BY_APPROVER_KIND = {
    'administration': 'admin_manager',
    'branch': 'branch_manager',
    'branch_accountant': 'branch_accountant',
}


def _settings() -> WorkflowWhatsAppSettings:
    return WorkflowWhatsAppSettings.get_solo()


def _send_to_user_or_role_fallback(
    *,
    user,
    role_key: str,
    message: str,
    event_type: str,
    related_action=None,
):
    log = dispatcher.send_to_user(
        user=user,
        message=message,
        event_type=event_type,
        related_action=related_action,
    )
    if log and log.status != WhatsAppMessageLog.Status.SKIPPED:
        return log

    phones = _settings().phones_for_roles(role_key)
    if not phones:
        return log

    logs = dispatcher.send_to_phones(
        phones=phones,
        message=message,
        event_type=f'{event_type}.role_fallback',
        related_action=related_action,
    )
    return logs[0] if logs else log


def _related_action(obj):
    return obj if isinstance(obj, PendingAction) else None


def _event_prefix(obj) -> str:
    from apps.employees.models import EmploymentRequest

    if isinstance(obj, EmploymentRequest):
        return 'employment_request'
    return 'pending_action'


def notify_whatsapp_request_created(obj) -> None:
    """بث لمدير النظام ومدير الموارد عند رفع طلب."""
    try:
        settings_obj = _settings()
        if not settings_obj.is_enabled:
            return
        phones = settings_obj.phones_for_roles('system_admin', 'hr_manager')
        if not phones:
            return
        message = templates.build_workflow_created_broadcast_message(obj)
        prefix = _event_prefix(obj)
        dispatcher.send_to_phones(
            phones=phones,
            message=message,
            event_type=f'workflow.{prefix}.created.broadcast',
            related_action=_related_action(obj),
        )
    except Exception as exc:
        logger.warning('notify_whatsapp_request_created failed: %s', exc)


def notify_whatsapp_first_stage(obj, *, title: str = '', message: str = '') -> None:
    """إشعار المعتمد الأول أو محاسبي الفرع."""
    try:
        settings_obj = _settings()
        if not settings_obj.is_enabled:
            return

        from apps.core.services.approval_routing import resolve_first_approver
        from apps.employees.services.cash_shortage_access import branch_accountants_for_branch

        text = templates.build_workflow_first_stage_message(obj, title=title, message=message)
        prefix = _event_prefix(obj)
        related = _related_action(obj)

        if isinstance(obj, PendingAction) and obj.action_type == PendingAction.ActionType.CASH_SHORTAGE:
            branch_id = obj.branch_id or (obj.employee.branch_id if obj.employee_id else None)
            accountants = list(branch_accountants_for_branch(branch_id))
            sent_any = False
            for accountant in accountants:
                log = dispatcher.send_to_user(
                    user=accountant,
                    message=text,
                    event_type=f'workflow.{prefix}.first_stage.accountant',
                    related_action=related,
                )
                if log and log.status != WhatsAppMessageLog.Status.SKIPPED:
                    sent_any = True
            if not sent_any:
                dispatcher.send_to_phones(
                    phones=_settings().phones_for_roles('branch_accountant'),
                    message=text,
                    event_type=f'workflow.{prefix}.first_stage.accountant.role_fallback',
                    related_action=related,
                )
            return

        decision = resolve_first_approver(obj)
        if decision.recipient:
            role_key = _ROLE_KEY_BY_APPROVER_KIND.get(decision.kind, 'branch_manager')
            _send_to_user_or_role_fallback(
                user=decision.recipient,
                role_key=role_key,
                message=text,
                event_type=f'workflow.{prefix}.first_stage.approver',
                related_action=related,
            )
    except Exception as exc:
        logger.warning('notify_whatsapp_first_stage failed: %s', exc)


def notify_whatsapp_pending_gm(obj) -> None:
    """إشعار مدير الموارد بعد موافقة المرحلة الأولى."""
    try:
        settings_obj = _settings()
        if not settings_obj.is_enabled:
            return
        phones = settings_obj.phones_for_roles('hr_manager')
        if not phones:
            return
        message = templates.build_workflow_pending_gm_message(obj)
        prefix = _event_prefix(obj)
        dispatcher.send_to_phones(
            phones=phones,
            message=message,
            event_type=f'workflow.{prefix}.pending_gm',
            related_action=_related_action(obj),
        )
    except Exception as exc:
        logger.warning('notify_whatsapp_pending_gm failed: %s', exc)


def notify_whatsapp_officer_assigned(obj, officer) -> None:
    """إشعار الأخصائي عند إسناد الطلب."""
    try:
        settings_obj = _settings()
        if not settings_obj.is_enabled:
            return
        if not officer:
            return
        message = templates.build_workflow_officer_assigned_message(obj, officer)
        prefix = _event_prefix(obj)
        _send_to_user_or_role_fallback(
            user=officer,
            role_key='hr_officer',
            message=message,
            event_type=f'workflow.{prefix}.officer_assigned',
            related_action=_related_action(obj),
        )
    except Exception as exc:
        logger.warning('notify_whatsapp_officer_assigned failed: %s', exc)


def notify_whatsapp_settlement_executed(action, execution_message: str = '') -> None:
    """بث لمدير النظام ومدير الموارد عند تنفيذ تصفية (مباشرة أو بعد الموافقات)."""
    from apps.core.models import PendingAction

    if not isinstance(action, PendingAction):
        return
    if action.action_type not in (
        PendingAction.ActionType.END_OF_SERVICE,
        PendingAction.ActionType.TERMINATE,
    ):
        return
    try:
        settings_obj = _settings()
        if not settings_obj.is_enabled:
            return
        phones = settings_obj.phones_for_roles('system_admin', 'hr_manager')
        if not phones:
            return
        message = templates.build_workflow_settlement_executed_message(action, execution_message)
        dispatcher.send_to_phones(
            phones=phones,
            message=message,
            event_type='workflow.pending_action.executed.settlement',
            related_action=action,
        )
    except Exception as exc:
        logger.warning('notify_whatsapp_settlement_executed failed: %s', exc)
