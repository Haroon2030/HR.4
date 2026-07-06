"""إرسال واتساب لطلبات الصيانة."""
from __future__ import annotations

import logging

from apps.core.services.whatsapp import dispatcher
from apps.maintenance.services import whatsapp_templates
from apps.maintenance.services.recipients import branch_manager_for_request, maintenance_manager_users
from apps.setup.models import WorkflowWhatsAppSettings

logger = logging.getLogger(__name__)


def _settings():
    return WorkflowWhatsAppSettings.get_solo()


def _is_enabled() -> bool:
    try:
        return _settings().is_enabled
    except Exception:
        return False


def notify_maintenance_created(req) -> None:
    if not _is_enabled():
        return
    message = whatsapp_templates.build_maintenance_created_message(req)
    phones_sent = set()

    for user in maintenance_manager_users():
        log = dispatcher.send_to_user(
            user=user,
            message=message,
            event_type='maintenance.request.created',
        )
        if log and log.phone:
            phones_sent.add(log.phone)

    fallback = _settings().phones_for_roles('maintenance_manager')
    extra = [p for p in fallback if p not in phones_sent]
    if extra:
        dispatcher.send_to_phones(
            phones=extra,
            message=message,
            event_type='maintenance.request.created.role_fallback',
        )


def notify_maintenance_assigned(req) -> None:
    if not _is_enabled():
        return
    worker = req.assigned_worker
    if not worker:
        return
    phone = worker.effective_phone
    if not phone:
        return
    message = whatsapp_templates.build_maintenance_assigned_message(req)
    dispatcher.send_to_phones(
        phones=[phone],
        message=message,
        event_type='maintenance.request.assigned',
    )


def notify_maintenance_worker_reported(req) -> None:
    if not _is_enabled():
        return
    message = whatsapp_templates.build_maintenance_worker_reported_message(req)
    phones_sent = set()
    for user in maintenance_manager_users():
        log = dispatcher.send_to_user(
            user=user,
            message=message,
            event_type='maintenance.request.worker_reported',
        )
        if log and log.phone:
            phones_sent.add(log.phone)
    fallback = _settings().phones_for_roles('maintenance_manager')
    extra = [p for p in fallback if p not in phones_sent]
    if extra:
        dispatcher.send_to_phones(
            phones=extra,
            message=message,
            event_type='maintenance.request.worker_reported.role_fallback',
        )


def notify_maintenance_manager_closed(req) -> None:
    if not _is_enabled():
        return
    message = whatsapp_templates.build_maintenance_manager_closed_message(req)
    manager = branch_manager_for_request(req)
    if manager:
        dispatcher.send_to_user(
            user=manager,
            message=message,
            event_type='maintenance.request.manager_closed',
        )
    else:
        fallback = _settings().phones_for_roles('branch_manager')
        if fallback:
            dispatcher.send_to_phones(
                phones=fallback,
                message=message,
                event_type='maintenance.request.manager_closed.role_fallback',
            )
