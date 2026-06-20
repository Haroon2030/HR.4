"""إرسال تقرير العمليات PDF عبر WhatsApp (Evolution API)."""
from __future__ import annotations

import logging
from datetime import date

from django.conf import settings

from apps.core.models import WhatsAppMessageLog
from apps.core.services.operations_report_data import OperationsReportBundle
from apps.core.services.operations_report_pdf import build_operations_report_pdf
from apps.core.services.whatsapp import client, phone_utils
from apps.setup.models import OperationsReportSettings

logger = logging.getLogger(__name__)


def _pdf_filename(bundle: OperationsReportBundle, report_date: date) -> str:
    role_suffix = bundle.role_key if bundle.role_key and bundle.role_key != 'full' else 'full'
    return f'operations-report-{role_suffix}-{report_date.isoformat()}.pdf'


def _build_caption(bundle: OperationsReportBundle, report_date: date) -> str:
    completed_total = sum(len(s.completed_rows) for s in bundle.sections)
    pending_total = sum(len(s.pending_rows) for s in bundle.sections)
    return (
        f'{bundle.report_title}\n'
        f'التاريخ: {report_date.isoformat()}\n'
        f'مُنجزة: {completed_total} | معلّقة: {pending_total}'
    )


def _log_whatsapp(
    *,
    phone: str,
    event_type: str,
    message: str,
    status: str,
    response='',
    error='',
) -> WhatsAppMessageLog:
    return WhatsAppMessageLog.objects.create(
        employee=None,
        phone=phone,
        event_type=event_type,
        message=message[:4000],
        status=status,
        response=str(response)[:2000],
        error=str(error)[:2000],
    )


def whatsapp_delivery_ready() -> bool:
    return bool(
        getattr(settings, 'WHATSAPP_ENABLED', False)
        and client.is_configured()
    )


def send_operations_report_whatsapp(
    *,
    bundle: OperationsReportBundle,
    phone: str,
    report_date: date,
    settings_obj: OperationsReportSettings,
    pdf_bytes: bytes | None = None,
    force: bool = False,
) -> bool:
    """يرسل PDF لتقرير العمليات. يُرجع True عند النجاح."""
    if not force and not settings_obj.send_via_whatsapp:
        return False

    if not getattr(settings, 'WHATSAPP_ENABLED', False):
        _log_whatsapp(
            phone=phone,
            event_type=f'operations_report.{bundle.role_key or "full"}',
            message=_build_caption(bundle, report_date),
            status=WhatsAppMessageLog.Status.SKIPPED,
            error='whatsapp_disabled',
        )
        return False

    normalized = phone_utils.normalize_phone(phone)
    if not normalized:
        _log_whatsapp(
            phone='',
            event_type=f'operations_report.{bundle.role_key or "full"}',
            message=_build_caption(bundle, report_date),
            status=WhatsAppMessageLog.Status.SKIPPED,
            error='no_phone',
        )
        return False

    if not client.is_configured():
        _log_whatsapp(
            phone=normalized,
            event_type=f'operations_report.{bundle.role_key or "full"}',
            message=_build_caption(bundle, report_date),
            status=WhatsAppMessageLog.Status.SKIPPED,
            error='not_configured',
        )
        return False

    caption = _build_caption(bundle, report_date)
    filename = _pdf_filename(bundle, report_date)
    event_type = f'operations_report.{bundle.role_key or "full"}'

    try:
        pdf = pdf_bytes
        if pdf is None:
            pdf = build_operations_report_pdf(
                report_date=report_date,
                bundle=bundle,
                include_pending=settings_obj.include_pending,
                include_completed=settings_obj.include_completed,
            )
        response = client.send_document(
            phone=normalized,
            pdf_bytes=pdf,
            file_name=filename,
            caption=caption,
        )
        _log_whatsapp(
            phone=normalized,
            event_type=event_type,
            message=caption,
            status=WhatsAppMessageLog.Status.SENT,
            response=response,
        )
        return True
    except client.EvolutionAPIError as exc:
        logger.warning('WhatsApp operations report failed for %s: %s', normalized, exc)
        _log_whatsapp(
            phone=normalized,
            event_type=event_type,
            message=caption,
            status=WhatsAppMessageLog.Status.FAILED,
            error=str(exc),
            response=getattr(exc, 'payload', '') or '',
        )
        return False
    except Exception as exc:
        logger.warning('WhatsApp operations report failed for %s: %s', normalized, exc)
        _log_whatsapp(
            phone=normalized,
            event_type=event_type,
            message=caption,
            status=WhatsAppMessageLog.Status.FAILED,
            error=str(exc),
        )
        return False
