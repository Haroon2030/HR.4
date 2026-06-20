"""إرسال تقرير العمليات PDF يومياً (cron)."""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.services.operations_report_data import bundle_has_content, collect_operations_report
from apps.core.services.operations_report_mail import build_and_send_operations_report
from apps.core.services.operations_report_schedule import (
    format_send_time,
    resolve_operations_report_date,
    scheduled_send_due,
)
from apps.setup.models import OperationsReportSettings
from apps.setup.operations_report_recipients import OPERATIONS_REPORT_RECIPIENT_ROLES

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'يبني تقرير PDF للعمليات المعلّقة والمُنجزة ويرسله إلى المستلمين '
        '(بريد و/أو واتساب) من إعدادات تهيئة النظام.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-email',
            action='store_true',
            help='إرسال البريد فعلياً (مطلوب من cron).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض الملخص دون إرسال.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='تجاهل فحص الساعة والتكرار (للاختبار اليدوي).',
        )
        parser.add_argument(
            '--recipient',
            default='',
            help='بريد مستلم بديل (للاختبار — تقرير شامل).',
        )
        parser.add_argument(
            '--recipient-phone',
            default='',
            help='جوال واتساب بديل (للاختبار — تقرير شامل).',
        )
        parser.add_argument(
            '--verbose-skip',
            action='store_true',
            help='طباعة سبب التخطي حتى خارج وقت الإرسال (للتشخيص).',
        )

    def handle(self, *args, **options):
        send_email = bool(options['send_email'])
        dry_run = bool(options['dry_run'])
        force = bool(options['force'])
        recipient_override = (options.get('recipient') or '').strip()
        recipient_phone_override = (options.get('recipient_phone') or '').strip()
        verbose_skip = bool(options['verbose_skip'])

        solo = OperationsReportSettings.get_solo()
        now = timezone.localtime()

        if not solo.is_enabled and not force and not recipient_override and not recipient_phone_override:
            msg = 'تخطي: الإرسال التلقائي غير مفعّل في إعدادات تقرير العمليات.'
            logger.info(msg)
            if verbose_skip:
                self.stdout.write(msg)
            return

        email_map = solo.recipient_emails_map()
        if recipient_override:
            target_roles = [('test', recipient_override)]
        elif recipient_phone_override:
            target_roles = [('test_phone', recipient_phone_override)]
        else:
            target_roles = [
                (rk, (email_map.get(rk) or '').strip())
                for rk, _label in OPERATIONS_REPORT_RECIPIENT_ROLES
                if (email_map.get(rk) or '').strip()
            ]

        if not target_roles:
            phone_map = solo.recipient_phones_map()
            target_roles = [
                (rk, (phone_map.get(rk) or '').strip())
                for rk, _label in OPERATIONS_REPORT_RECIPIENT_ROLES
                if solo.send_via_whatsapp and (phone_map.get(rk) or '').strip()
            ]

        if not target_roles:
            msg = 'تخطي: لا يوجد بريد أو جوال مستلم — حدّده من صفحة إعدادات تقرير العمليات.'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
            return

        if not force and not recipient_override and not recipient_phone_override:
            due, due_reason = scheduled_send_due(now, solo)
            if not due:
                msg = (
                    f'تخطي ({due_reason}): وقت الإرسال {format_send_time(solo.send_time)} '
                    f'{timezone.get_current_timezone_name()} — الآن {now.strftime("%H:%M:%S")}.'
                )
                logger.info(msg)
                if verbose_skip:
                    self.stdout.write(msg)
                return

        report_date = resolve_operations_report_date(
            now,
            solo.send_time,
            manual=bool(recipient_override or recipient_phone_override or force),
        )
        reports_to_send = 0

        logger.info(
            'بدء تقرير العمليات المجدول — report_date=%s now=%s — مستلمون: %s',
            report_date.isoformat(),
            now.strftime('%Y-%m-%d %H:%M:%S'),
            len(target_roles),
        )

        for role_key, email in target_roles:
            rk = None if role_key == 'test' else role_key
            bundle = collect_operations_report(
                report_date=report_date,
                include_pending=solo.include_pending,
                include_completed=solo.include_completed,
                role_key=rk,
            )
            if recipient_override or recipient_phone_override:
                has_content = True
            elif not bundle_has_content(
                bundle,
                include_pending=solo.include_pending,
                include_completed=solo.include_completed,
            ):
                self.stdout.write(f'  [{role_key}] لا بيانات — تخطي ({email})')
                continue

            completed_total = sum(len(s.completed_rows) for s in bundle.sections)
            pending_total = sum(len(s.pending_rows) for s in bundle.sections)
            self.stdout.write(
                f'تقرير {report_date} [{bundle.report_title}]: '
                f'معلّقة={pending_total} | مُنجزة={completed_total} → {email}'
            )
            for section in bundle.sections:
                if section.completed_rows or section.pending_rows:
                    self.stdout.write(
                        f'  - {section.title}: اليوم={len(section.completed_rows)} معلّق={len(section.pending_rows)}'
                    )
            reports_to_send += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'dry-run — {reports_to_send} تقرير(ات) — لم يُرسل.'))
            return

        if not send_email:
            self.stdout.write(self.style.WARNING('أضف --send-email لإرسال التقرير فعلياً (بريد و/أو واتساب).'))
            return

        try:
            send_result = build_and_send_operations_report(
                report_date=report_date,
                recipient=recipient_override or None,
                recipient_phone=recipient_phone_override or None,
                settings_obj=solo,
                force=bool(recipient_override or recipient_phone_override or force),
            )
            sent = send_result.sent
        except Exception as exc:
            logger.exception('فشل إرسال تقرير العمليات المجدول')
            self.stdout.write(self.style.ERROR(f'فشل الإرسال: {exc}'))
            raise

        if sent:
            solo.last_sent_at = now
            solo.save(update_fields=['last_sent_at'])
            logger.info('تم إرسال تقرير العمليات المجدول بنجاح.')
            self.stdout.write(self.style.SUCCESS('تم إرسال تقرير العمليات بنجاح.'))
        else:
            msg = f'لم يُرسل أي تقرير (لا بيانات لتاريخ {report_date} أو لا مستلمين).'
            if send_result.errors:
                msg = f'{msg} {" — ".join(send_result.errors[:2])}'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
