"""فحص جاهزية إرسال البريد (SMTP) — للتشخيص في الإنتاج."""
from __future__ import annotations

from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand

from apps.core.services.email_delivery import (
    SmtpConnectionError,
    SmtpNotConfiguredError,
    deliver_email_message,
    email_delivery_status,
    ensure_smtp_ready,
    resolve_from_email,
)


class Command(BaseCommand):
    help = 'يفحص ضبط SMTP والاتصال الفعلي بمزود البريد.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verify-connection',
            action='store_true',
            help='محاولة فتح اتصال SMTP (مصادقة).',
        )
        parser.add_argument(
            '--send-to',
            default='',
            help='إرسال رسالة نصية تجريبية بدون مرفق (للتأكد من التسليم).',
        )

    def handle(self, *args, **options):
        status = email_delivery_status()
        self.stdout.write(f"Backend: {status['backend']}")
        self.stdout.write(f"Mode: {status['mode']}")
        self.stdout.write(f"Host: {status['host'] or '—'}")
        self.stdout.write(f"From (env): {status['from_email'] or '—'}")
        self.stdout.write(f"From (effective): {status.get('effective_from') or resolve_from_email()}")
        self.stdout.write(f"SMTP ready: {status['smtp_ready']}")

        if status['from_warning']:
            self.stdout.write(self.style.WARNING(status['from_warning']))

        if not status['smtp_ready']:
            self.stdout.write(self.style.ERROR(
                'SMTP غير مضبوط — لن يُرسل بريد حقيقي. راجع Environment في Dokploy.'
            ))
            raise SystemExit(1)

        send_to = (options.get('send_to') or '').strip()
        verify = bool(options['verify_connection']) or bool(send_to)

        if not verify:
            self.stdout.write(self.style.SUCCESS(
                'SMTP مضبوظ — أضف --verify-connection أو --send-to لاختبار أعمق.'
            ))
            return

        try:
            ensure_smtp_ready(verify_connection=True)
        except SmtpNotConfiguredError as exc:
            self.stdout.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc
        except SmtpConnectionError as exc:
            self.stdout.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc

        self.stdout.write(self.style.SUCCESS('تم الاتصال بـ SMTP بنجاح.'))

        if not send_to:
            return

        msg = EmailMessage(
            subject='HR Pro - اختبار بريد SMTP',
            body=(
                'رسالة اختبار نصية من نظام HR Pro.\n'
                'إذا وصلتك هذه الرسالة فالتسليم يعمل.\n'
                'جرّب بعدها تقرير العمليات (PDF) وتحقق من Spam.'
            ),
            to=[send_to],
        )
        try:
            deliver_email_message(msg, verify_connection=False, log_context='smtp_test')
        except (SmtpNotConfiguredError, SmtpConnectionError) as exc:
            self.stdout.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'فشل إرسال الاختبار: {exc}'))
            raise SystemExit(1) from exc

        self.stdout.write(self.style.SUCCESS(f'تم إرسال رسالة اختبار إلى {send_to}'))
