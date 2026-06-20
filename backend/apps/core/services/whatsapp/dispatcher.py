"""Dispatch WhatsApp notifications for HR workflow events."""
from __future__ import annotations

import logging

from django.conf import settings

from apps.core.models import PendingAction, WhatsAppMessageLog
from apps.core.services.whatsapp import client, phone_utils, templates

logger = logging.getLogger(__name__)


def _log_message(
    *,
    employee,
    phone: str,
    event_type: str,
    message: str,
    status: str,
    related_action=None,
    response='',
    error='',
) -> WhatsAppMessageLog:
    return WhatsAppMessageLog.objects.create(
        employee=employee,
        phone=phone,
        event_type=event_type,
        message=message[:4000],
        status=status,
        related_action=related_action,
        response=str(response)[:2000],
        error=str(error)[:2000],
    )


def send_to_employee(
    *,
    employee,
    message: str,
    event_type: str,
    related_action=None,
) -> WhatsAppMessageLog | None:
    if not getattr(settings, 'WHATSAPP_ENABLED', False):
        return None

    phone = phone_utils.normalize_phone(getattr(employee, 'phone', ''))
    if not phone:
        return _log_message(
            employee=employee,
            phone='',
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.SKIPPED,
            related_action=related_action,
            error='no_phone',
        )

    if not client.is_configured():
        return _log_message(
            employee=employee,
            phone=phone,
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.SKIPPED,
            related_action=related_action,
            error='not_configured',
        )

    try:
        response = client.send_text(phone=phone, text=message)
        return _log_message(
            employee=employee,
            phone=phone,
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.SENT,
            related_action=related_action,
            response=response,
        )
    except client.EvolutionAPIError as exc:
        logger.warning('WhatsApp send failed for employee %s: %s', employee.pk, exc)
        return _log_message(
            employee=employee,
            phone=phone,
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.FAILED,
            related_action=related_action,
            error=str(exc),
            response=getattr(exc, 'payload', '') or '',
        )
    except Exception as exc:
        logger.warning('WhatsApp send failed for employee %s: %s', employee.pk, exc)
        return _log_message(
            employee=employee,
            phone=phone,
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.FAILED,
            related_action=related_action,
            error=str(exc),
        )


def notify_whatsapp_action_executed(action: PendingAction, execution_message: str = '') -> WhatsAppMessageLog | None:
    """Send WhatsApp to employee when a PendingAction is executed successfully."""
    if not action or not action.employee_id:
        return None

    message = templates.build_executed_message(action, execution_message)
    event_type = f'pending_action.executed.{action.action_type}'
    return send_to_employee(
        employee=action.employee,
        message=message,
        event_type=event_type,
        related_action=action,
    )
