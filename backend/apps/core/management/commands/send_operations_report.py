"""إرسال تقرير العمليات PDF يومياً (cron)."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.services.operations_report_mail import build_and_send_operations_report
from apps.setup.models import OperationsReportSettings


class Command(BaseCommand):
    help = (
        'يبني تقرير PDF للعمليات المعلّقة والمُنجزة ويرسله إلى البريد المُحدّد '
        'في إعدادات تهيئة النظام (setup/operations-report/).'
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
            help='بريد مستلم بديل (للاختبار).',
        )

    def handle(self, *args, **options):
        send_email = bool(options['send_email'])
        dry_run = bool(options['dry_run'])
        force = bool(options['force'])
        recipient_override = (options.get('recipient') or '').strip()

        solo = OperationsReportSettings.get_solo()
        now = timezone.localtime()

        if not solo.is_enabled and not force and not recipient_override:
            self.stdout.write('الإرسال التلقائي غير مفعّل — تخطي.')
            return

        target_email = recipient_override or (solo.recipient_email or '').strip()
        if not target_email:
            self.stdout.write(self.style.WARNING('لا يوجد بريد مستلم — حدّده من صفحة إعدادات تقرير العمليات.'))
            return

        if not force and solo.send_hour != now.hour:
            self.stdout.write(
                f'ليست ساعة الإرسال ({solo.send_hour}:00) — الآن {now.hour}:{now.minute:02d} — تخطي.'
            )
            return

        if not force and solo.last_sent_at:
            last = timezone.localtime(solo.last_sent_at)
            if last.date() == now.date() and last.hour == solo.send_hour:
                self.stdout.write('تم الإرسال مسبقاً اليوم في هذه الساعة — تخطي.')
                return

        from apps.core.services.operations_report_data import collect_operations_report

        report_date = now.date()
        bundle = collect_operations_report(
            report_date=report_date,
            include_pending=solo.include_pending,
            include_completed=solo.include_completed,
        )
        completed_total = sum(len(s.completed_rows) for s in bundle.sections) + len(bundle.employment_completed)
        pending_total = sum(len(s.pending_rows) for s in bundle.sections) + len(bundle.employment_pending)
        self.stdout.write(
            f'تقرير {report_date}: معلّقة={pending_total} | مُنجزة={completed_total} → {target_email}'
        )
        for section in bundle.sections:
            if section.completed_rows or section.pending_rows:
                self.stdout.write(
                    f'  - {section.title}: اليوم={len(section.completed_rows)} معلّق={len(section.pending_rows)}'
                )

        if dry_run:
            self.stdout.write(self.style.SUCCESS('dry-run — لم يُرسل بريد.'))
            return

        if not send_email:
            self.stdout.write(self.style.WARNING('أضف --send-email لإرسال البريد فعلياً.'))
            return

        try:
            sent = build_and_send_operations_report(
                report_date=report_date,
                recipient=recipient_override or None,
                settings_obj=solo,
                force=True,
            )
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'فشل الإرسال: {exc}'))
            raise

        if sent:
            solo.last_sent_at = now
            solo.save(update_fields=['last_sent_at'])
            self.stdout.write(self.style.SUCCESS('تم إرسال تقرير العمليات بنجاح.'))
        else:
            self.stdout.write(self.style.WARNING('لم يُرسل التقرير.'))
