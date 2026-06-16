"""إرسال تقرير العمليات PDF بالبريد — تقرير مخصّص لكل دور."""
from __future__ import annotations

import logging
from datetime import date

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.core.services.email_delivery import deliver_email_message, ensure_smtp_ready
from apps.core.services.operations_report_data import (
    OperationsReportBundle,
    bundle_has_content,
    collect_operations_report,
)
from apps.core.services.operations_report_pdf import build_operations_report_pdf
from apps.setup.models import OperationsReportSettings
from apps.setup.operations_report_recipients import OPERATIONS_REPORT_RECIPIENT_ROLES

logger = logging.getLogger(__name__)


def _build_email_body(bundle: OperationsReportBundle, report_date: date) -> str:
    completed_total = sum(len(s.completed_rows) for s in bundle.sections)
    pending_total = sum(len(s.pending_rows) for s in bundle.sections)
    section_titles = '، '.join(s.title for s in bundle.sections)

    body_lines = [
        f'مرفق {bundle.report_title} (PDF).',
        f'الأقسام: {section_titles or "—"}.',
        '',
        f'تاريخ التقرير: {report_date.isoformat()}',
        f'إجمالي عمليات اليوم: {completed_total}',
        f'إجمالي المعلّق: {pending_total}',
        '',
        '— تفصيل اليوم —',
    ]
    for section in bundle.sections:
        if section.completed_rows:
            body_lines.append(f'  • {section.title}: {len(section.completed_rows)}')
    body_lines.extend(['', '— نظام الموارد البشرية'])
    return '\n'.join(body_lines)


def _send_operations_report_email(
    *,
    bundle: OperationsReportBundle,
    recipients: list[str],
    report_date: date,
    settings_obj: OperationsReportSettings,
) -> None:
    pdf_bytes = build_operations_report_pdf(
        report_date=report_date,
        bundle=bundle,
        include_pending=settings_obj.include_pending,
        include_completed=settings_obj.include_completed,
    )

    subject = f'{bundle.report_title} — {report_date.isoformat()}'
    msg = EmailMessage(
        subject=subject,
        body=_build_email_body(bundle, report_date),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    role_suffix = bundle.role_key if bundle.role_key and bundle.role_key != 'full' else 'full'
    filename = f'operations-report-{role_suffix}-{report_date.isoformat()}.pdf'
    msg.attach(filename, pdf_bytes, 'application/pdf')
    deliver_email_message(msg, log_context=f'operations_report:{role_suffix}')


def build_and_send_operations_report(
    *,
    report_date: date | None = None,
    recipient: str | None = None,
    settings_obj: OperationsReportSettings | None = None,
    force: bool = False,
    role_key: str | None = None,
) -> bool:
    """
    يبني PDF ويرسله. يُرجع True عند نجاح إرسال تقرير واحد على الأقل.
    عند تحديد recipient: يُرسل التقرير الشامل للبريد المحدد (اختبار).
    """
    settings_obj = settings_obj or OperationsReportSettings.get_solo()
    report_date = report_date or timezone.localdate()

    if settings_obj.is_enabled is False and not force and recipient is None:
        logger.info('تخطي تقرير العمليات: الإرسال التلقائي غير مفعّل.')
        return False

    ensure_smtp_ready(verify_connection=True)

    if recipient:
        bundle = collect_operations_report(
            report_date=report_date,
            include_pending=settings_obj.include_pending,
            include_completed=settings_obj.include_completed,
            role_key=None,
        )
        _send_operations_report_email(
            bundle=bundle,
            recipients=[recipient.strip()],
            report_date=report_date,
            settings_obj=settings_obj,
        )
        return True

    email_map = settings_obj.recipient_emails_map()
    sent_any = False

    for rk, _label in OPERATIONS_REPORT_RECIPIENT_ROLES:
        email = (email_map.get(rk) or '').strip()
        if not email:
            continue

        bundle = collect_operations_report(
            report_date=report_date,
            include_pending=settings_obj.include_pending,
            include_completed=settings_obj.include_completed,
            role_key=rk,
        )
        if not bundle_has_content(
            bundle,
            include_pending=settings_obj.include_pending,
            include_completed=settings_obj.include_completed,
        ):
            logger.info('تخطي تقرير فارغ للدور: %s', rk)
            continue

        _send_operations_report_email(
            bundle=bundle,
            recipients=[email],
            report_date=report_date,
            settings_obj=settings_obj,
        )
        sent_any = True

    if not sent_any:
        logger.info('تخطي تقرير العمليات: لا يوجد بريد مستلم أو لا توجد بيانات.')
    return sent_any
