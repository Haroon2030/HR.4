"""إرسال تقرير العمليات PDF بالبريد."""
from __future__ import annotations

import logging
from datetime import date

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.core.services.operations_report_data import collect_operations_report
from apps.core.services.operations_report_pdf import build_operations_report_pdf
from apps.setup.models import OperationsReportSettings

logger = logging.getLogger(__name__)


def build_and_send_operations_report(
    *,
    report_date: date | None = None,
    recipient: str | None = None,
    settings_obj: OperationsReportSettings | None = None,
    force: bool = False,
) -> bool:
    """
    يبني PDF ويرسله. يُرجع True عند نجاح الإرسال.
    """
    settings_obj = settings_obj or OperationsReportSettings.get_solo()
    report_date = report_date or timezone.localdate()
    to_email = (recipient or settings_obj.recipient_email or '').strip()
    if not to_email:
        logger.info('تخطي تقرير العمليات: لا يوجد بريد مستلم.')
        return False

    if settings_obj.is_enabled is False and not force and recipient is None:
        logger.info('تخطي تقرير العمليات: الإرسال التلقائي غير مفعّل.')
        return False

    bundle = collect_operations_report(
        report_date=report_date,
        include_pending=settings_obj.include_pending,
        include_completed=settings_obj.include_completed,
    )

    pdf_bytes = build_operations_report_pdf(
        report_date=report_date,
        bundle=bundle,
        include_pending=settings_obj.include_pending,
        include_completed=settings_obj.include_completed,
    )

    completed_total = sum(len(s.completed_rows) for s in bundle.sections) + len(bundle.employment_completed)
    pending_total = sum(len(s.pending_rows) for s in bundle.sections) + len(bundle.employment_pending)

    subject = f'تقرير العمليات اليومي — {report_date.isoformat()}'
    body_lines = [
        'مرفق تقرير العمليات اليومي (PDF) — أقسام: سلف، إجازات، تنقلات، تصفيات، غيابات، إضافات، تعديلات راتب.',
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
    if bundle.employment_completed:
        body_lines.append(f'  • توظيف: {len(bundle.employment_completed)}')
    body_lines.extend(['', '— نظام الموارد البشرية'])
    msg = EmailMessage(
        subject=subject,
        body='\n'.join(body_lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    filename = f'operations-report-{report_date.isoformat()}.pdf'
    msg.attach(filename, pdf_bytes, 'application/pdf')
    msg.send(fail_silently=False)
    logger.info('تم إرسال تقرير العمليات إلى %s', to_email)
    return True
