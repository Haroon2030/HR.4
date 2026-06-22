"""إشعارات واتساب لمراحل دورة الموافقات."""
from __future__ import annotations

import logging

from apps.core.models import PendingAction
from apps.core.services.whatsapp import dispatcher, templates
from apps.setup.models import WorkflowWhatsAppSettings

logger = logging.getLogger(__name__)


def _settings() -> WorkflowWhatsAppSettings:
    return WorkflowWhatsAppSettings.get_solo()


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
            for accountant in branch_accountants_for_branch(branch_id):
                dispatcher.send_to_user(
                    user=accountant,
                    message=text,
                    event_type=f'workflow.{prefix}.first_stage.accountant',
                    related_action=related,
                )
            return

        decision = resolve_first_approver(obj)
        if decision.recipient:
            dispatcher.send_to_user(
                user=decision.recipient,
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
        dispatcher.send_to_user(
            user=officer,
            message=message,
            event_type=f'workflow.{prefix}.officer_assigned',
            related_action=_related_action(obj),
        )
    except Exception as exc:
        logger.warning('notify_whatsapp_officer_assigned failed: %s', exc)
