"""فحص جاهزية إرسال البريد (SMTP) — للتشخيص في الإنتاج."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.services.email_delivery import (
    SmtpConnectionError,
    SmtpNotConfiguredError,
    email_delivery_status,
    ensure_smtp_ready,
)


class Command(BaseCommand):
    help = 'يفحص ضبط SMTP والاتصال الفعلي بمزود البريد.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verify-connection',
            action='store_true',
            help='محاولة فتح اتصال SMTP (مصادقة).',
        )

    def handle(self, *args, **options):
        status = email_delivery_status()
        self.stdout.write(f"Backend: {status['backend']}")
        self.stdout.write(f"Mode: {status['mode']}")
        self.stdout.write(f"Host: {status['host'] or '—'}")
        self.stdout.write(f"From: {status['from_email'] or '—'}")
        self.stdout.write(f"SMTP ready: {status['smtp_ready']}")

        if status['from_warning']:
            self.stdout.write(self.style.WARNING(status['from_warning']))

        if not status['smtp_ready']:
            self.stdout.write(self.style.ERROR(
                'SMTP غير مضبوط — لن يُرسل بريد حقيقي. راجع Environment في Dokploy.'
            ))
            raise SystemExit(1)

        if not options['verify_connection']:
            self.stdout.write(self.style.SUCCESS('SMTP مضبوظ — أضف --verify-connection لاختبار الاتصال.'))
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
