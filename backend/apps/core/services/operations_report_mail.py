"""إرسال تقرير العمليات PDF — بريد وواتساب."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
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
from apps.core.services.operations_report_whatsapp import send_operations_report_whatsapp
from apps.setup.models import OperationsReportSettings
from apps.setup.operations_report_recipients import OPERATIONS_REPORT_RECIPIENT_ROLES

logger = logging.getLogger(__name__)


@dataclass
class OperationsReportSendResult:
    sent: bool = False
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        message = (message or '').strip()
        if message and message not in self.errors:
            self.errors.append(message)


def _build_email_body(bundle: OperationsReportBundle, report_date: date) -> str:
    completed_total = sum(len(s.completed_rows) for s in bundle.sections)
    pending_total = sum(len(s.pending_rows) for s in bundle.sections)
    section_titles = '، '.join(s.title for s in bundle.sections)

    body_lines = [
        f'مرفق {bundle.report_title} (PDF).',
        f'الأقسام: {section_titles or "-"}.',
        '',
        f'تاريخ التقرير: {report_date.isoformat()}',
        f'إجمالي عمليات اليوم: {completed_total}',
        f'إجمالي المعلّق: {pending_total}',
        '',
        '- تفصيل اليوم -',
    ]
    for section in bundle.sections:
        if section.completed_rows:
            body_lines.append(f'  • {section.title}: {len(section.completed_rows)}')
    body_lines.extend(['', '- نظام الموارد البشرية'])
    return '\n'.join(body_lines)


def _build_pdf(
    *,
    bundle: OperationsReportBundle,
    report_date: date,
    settings_obj: OperationsReportSettings,
) -> bytes:
    return build_operations_report_pdf(
        report_date=report_date,
        bundle=bundle,
        include_pending=settings_obj.include_pending,
        include_completed=settings_obj.include_completed,
    )


def _send_operations_report_email(
    *,
    bundle: OperationsReportBundle,
    recipients: list[str],
    report_date: date,
    settings_obj: OperationsReportSettings,
    pdf_bytes: bytes | None = None,
) -> None:
    pdf = pdf_bytes or _build_pdf(
        bundle=bundle,
        report_date=report_date,
        settings_obj=settings_obj,
    )

    subject = f'{bundle.report_title} - {report_date.isoformat()}'
    msg = EmailMessage(
        subject=subject,
        body=_build_email_body(bundle, report_date),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    role_suffix = bundle.role_key if bundle.role_key and bundle.role_key != 'full' else 'full'
    filename = f'operations-report-{role_suffix}-{report_date.isoformat()}.pdf'
    msg.attach(filename, pdf, 'application/pdf')
    deliver_email_message(msg, log_context=f'operations_report:{role_suffix}')


def _deliver_bundle(
    *,
    bundle: OperationsReportBundle,
    report_date: date,
    settings_obj: OperationsReportSettings,
    email: str = '',
    phone: str = '',
    send_email: bool = True,
    send_whatsapp: bool = False,
    pdf_bytes: bytes | None = None,
    force_whatsapp: bool = False,
    result: OperationsReportSendResult | None = None,
) -> bool:
    """يرسل التقرير عبر القنوات المفعّلة. يُرجع True عند نجاح قناة واحدة على الأقل."""
    sent = False
    pdf = pdf_bytes

    if send_email and email:
        try:
            if pdf is None:
                pdf = _build_pdf(bundle=bundle, report_date=report_date, settings_obj=settings_obj)
            _send_operations_report_email(
                bundle=bundle,
                recipients=[email.strip()],
                report_date=report_date,
                settings_obj=settings_obj,
                pdf_bytes=pdf,
            )
            sent = True
        except Exception as exc:
            if result is not None:
                result.add_error(f'فشل البريد إلى {email.strip()}: {exc}')
            logger.warning('Operations report email failed for %s: %s', email, exc)

    if send_whatsapp and phone:
        if pdf is None:
            pdf = _build_pdf(bundle=bundle, report_date=report_date, settings_obj=settings_obj)
        ok, err = send_operations_report_whatsapp(
            bundle=bundle,
            phone=phone,
            report_date=report_date,
            settings_obj=settings_obj,
            pdf_bytes=pdf,
            force=force_whatsapp,
        )
        if ok:
            sent = True
        elif result is not None and err:
            result.add_error(f'{phone.strip()}: {err}')

    return sent


def build_and_send_operations_report(
    *,
    report_date: date | None = None,
    recipient: str | None = None,
    recipient_phone: str | None = None,
    settings_obj: OperationsReportSettings | None = None,
    force: bool = False,
    role_key: str | None = None,
    send_email: bool = True,
    send_whatsapp: bool | None = None,
    allow_empty: bool = False,
) -> OperationsReportSendResult:
    """
    يبني PDF ويرسله.
    عند تحديد recipient / recipient_phone: إرسال تجريبي (تقرير شامل).
    """
    outcome = OperationsReportSendResult()
    settings_obj = settings_obj or OperationsReportSettings.get_solo()
    report_date = report_date or timezone.localdate()

    has_saved_emails = bool(settings_obj.active_recipient_emails())
    has_saved_phones = bool(settings_obj.active_recipient_phones())
    whatsapp_enabled = settings_obj.send_via_whatsapp if send_whatsapp is None else send_whatsapp
    if force and has_saved_phones:
        whatsapp_enabled = True

    if settings_obj.is_enabled is False and not force and recipient is None and recipient_phone is None:
        logger.info('تخطي تقرير العمليات: الإرسال التلقائي غير مفعّل.')
        outcome.add_error('الإرسال التلقائي غير مفعّل.')
        return outcome

    test_email = (recipient or '').strip()
    test_phone = (recipient_phone or '').strip()
    will_send_email = send_email and bool(test_email or (not test_phone and has_saved_emails))
    if will_send_email:
        try:
            ensure_smtp_ready(verify_connection=True)
        except Exception as exc:
            outcome.add_error(str(exc))
            if not (test_phone or (whatsapp_enabled and has_saved_phones)):
                return outcome
            send_email = False
            will_send_email = False

    force_whatsapp = force and bool(test_phone or has_saved_phones)

    if test_email or test_phone:
        bundle = collect_operations_report(
            report_date=report_date,
            include_pending=settings_obj.include_pending,
            include_completed=settings_obj.include_completed,
            role_key=role_key,
        )
        has_content = bundle_has_content(
            bundle,
            include_pending=settings_obj.include_pending,
            include_completed=settings_obj.include_completed,
        )
        if has_content or allow_empty:
            if _deliver_bundle(
                bundle=bundle,
                report_date=report_date,
                settings_obj=settings_obj,
                email=test_email,
                phone=test_phone,
                send_email=bool(test_email) and send_email,
                send_whatsapp=bool(test_phone),
                force_whatsapp=bool(test_phone) or force_whatsapp,
                result=outcome,
            ):
                outcome.sent = True
                return outcome
        if not has_content:
            outcome.add_error(f'لا توجد بيانات لتاريخ {report_date.isoformat()}.')
        return outcome

    email_map = settings_obj.recipient_emails_map()
    phone_map = settings_obj.recipient_phones_map()
    sent_any = False

    for rk, _label in OPERATIONS_REPORT_RECIPIENT_ROLES:
        email = (email_map.get(rk) or '').strip()
        phone = (phone_map.get(rk) or '').strip()
        if not email and not (whatsapp_enabled and phone):
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

        if _deliver_bundle(
            bundle=bundle,
            report_date=report_date,
            settings_obj=settings_obj,
            email=email,
            phone=phone,
            send_email=send_email,
            send_whatsapp=whatsapp_enabled,
            force_whatsapp=force_whatsapp,
            result=outcome,
        ):
            sent_any = True

    if not sent_any:
        full_bundle = collect_operations_report(
            report_date=report_date,
            include_pending=settings_obj.include_pending,
            include_completed=settings_obj.include_completed,
            role_key=None,
        )
        if bundle_has_content(
            full_bundle,
            include_pending=settings_obj.include_pending,
            include_completed=settings_obj.include_completed,
        ):
            seen_emails: set[str] = set()
            seen_phones: set[str] = set()
            for email in settings_obj.active_recipient_emails():
                norm = email.strip().lower()
                if not norm or norm in seen_emails:
                    continue
                seen_emails.add(norm)
                if _deliver_bundle(
                    bundle=full_bundle,
                    report_date=report_date,
                    settings_obj=settings_obj,
                    email=email.strip(),
                    phone='',
                    send_email=send_email,
                    send_whatsapp=False,
                    result=outcome,
                ):
                    sent_any = True

            if whatsapp_enabled:
                for phone in settings_obj.active_recipient_phones():
                    norm = phone.replace(' ', '').replace('-', '')
                    if not norm or norm in seen_phones:
                        continue
                    seen_phones.add(norm)
                    if _deliver_bundle(
                        bundle=full_bundle,
                        report_date=report_date,
                        settings_obj=settings_obj,
                        email='',
                        phone=phone,
                        send_email=False,
                        send_whatsapp=True,
                        force_whatsapp=force_whatsapp,
                        result=outcome,
                    ):
                        sent_any = True

            if sent_any:
                logger.info(
                    'تقرير العمليات: إرسال تقرير شامل احتياطي — لا بيانات في تقارير الأدوار المفلترة.'
                )

    if not sent_any and allow_empty:
        full_bundle = collect_operations_report(
            report_date=report_date,
            include_pending=settings_obj.include_pending,
            include_completed=settings_obj.include_completed,
            role_key=None,
        )
        for email in settings_obj.active_recipient_emails():
            if _deliver_bundle(
                bundle=full_bundle,
                report_date=report_date,
                settings_obj=settings_obj,
                email=email.strip(),
                phone='',
                send_email=send_email,
                send_whatsapp=False,
                result=outcome,
            ):
                sent_any = True
        if whatsapp_enabled:
            for phone in settings_obj.active_recipient_phones():
                if _deliver_bundle(
                    bundle=full_bundle,
                    report_date=report_date,
                    settings_obj=settings_obj,
                    email='',
                    phone=phone,
                    send_email=False,
                    send_whatsapp=True,
                    force_whatsapp=True,
                    result=outcome,
                ):
                    sent_any = True

    if not sent_any:
        logger.info('تخطي تقرير العمليات: لا يوجد مستلم أو فشل الإرسال.')
        if not outcome.errors:
            outcome.add_error('لم يُرسل عبر أي قناة — تحقق من المستلمين وضبط البريد أو واتساب.')
    outcome.sent = sent_any
    return outcome
