"""Dispatch WhatsApp notifications for HR workflow events."""
from __future__ import annotations

import logging

from django.conf import settings

from apps.core.models import PendingAction, WhatsAppMessageLog
from apps.core.services.whatsapp import client, phone_utils, templates

logger = logging.getLogger(__name__)


def _log_message(
    *,
    employee=None,
    recipient_user=None,
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
        recipient_user=recipient_user,
        phone=phone,
        event_type=event_type,
        message=message[:4000],
        status=status,
        related_action=related_action,
        response=str(response)[:2000],
        error=str(error)[:2000],
    )


def _whatsapp_ready() -> bool:
    if not getattr(settings, 'WHATSAPP_ENABLED', False):
        return False
    if not client.is_configured():
        return False
    try:
        from apps.setup.models import WorkflowWhatsAppSettings

        return bool(WorkflowWhatsAppSettings.get_solo().is_enabled)
    except Exception:
        return False


def _send_text(
    *,
    phone: str,
    message: str,
    event_type: str,
    employee=None,
    recipient_user=None,
    related_action=None,
) -> WhatsAppMessageLog | None:
    if not _whatsapp_ready():
        return None

    normalized = phone_utils.normalize_phone(phone)
    if not normalized:
        return _log_message(
            employee=employee,
            recipient_user=recipient_user,
            phone='',
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.SKIPPED,
            related_action=related_action,
            error='no_phone',
        )

    try:
        response = client.send_text(phone=normalized, text=message)
        return _log_message(
            employee=employee,
            recipient_user=recipient_user,
            phone=normalized,
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.SENT,
            related_action=related_action,
            response=response,
        )
    except client.EvolutionAPIError as exc:
        logger.warning('WhatsApp send failed (%s): %s', event_type, exc)
        return _log_message(
            employee=employee,
            recipient_user=recipient_user,
            phone=normalized,
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.FAILED,
            related_action=related_action,
            error=str(exc),
            response=getattr(exc, 'payload', '') or '',
        )
    except Exception as exc:
        logger.warning('WhatsApp send failed (%s): %s', event_type, exc)
        return _log_message(
            employee=employee,
            recipient_user=recipient_user,
            phone=normalized,
            event_type=event_type,
            message=message,
            status=WhatsAppMessageLog.Status.FAILED,
            related_action=related_action,
            error=str(exc),
        )


def send_to_user(
    *,
    user,
    message: str,
    event_type: str,
    related_action=None,
) -> WhatsAppMessageLog | None:
    if not user:
        return None
    from apps.core.models import UserProfile

    profile = UserProfile.objects.filter(user_id=user.pk).only('phone').first()
    phone = (profile.phone if profile else '') or ''
    return _send_text(
        phone=phone,
        message=message,
        event_type=event_type,
        recipient_user=user,
        related_action=related_action,
    )


def send_to_phones(
    *,
    phones: list[str],
    message: str,
    event_type: str,
    related_action=None,
) -> list[WhatsAppMessageLog]:
    logs: list[WhatsAppMessageLog] = []
    seen: set[str] = set()
    for raw in phones:
        normalized = phone_utils.normalize_phone(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        log = _send_text(
            phone=raw,
            message=message,
            event_type=event_type,
            related_action=related_action,
        )
        if log:
            logs.append(log)
    return logs


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

    return _send_text(
        phone=phone,
        message=message,
        event_type=event_type,
        employee=employee,
        related_action=related_action,
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
