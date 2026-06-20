"""Test Evolution API WhatsApp configuration and optional send."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.services.whatsapp import client


class Command(BaseCommand):
    help = 'يفحص ضبط Evolution API ويرسل رسالة تجريبية اختيارياً.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-to',
            default='',
            help='رقم جوال (مثال: 9665xxxxxxxx) لإرسال رسالة تجريبية.',
        )
        parser.add_argument(
            '--send-pdf',
            default='',
            help='رقم جوال لإرسال PDF تجريبي صغير (اختبار sendMedia).',
        )
        parser.add_argument(
            '--list-instances',
            action='store_true',
            help='عرض instances المتاحة من Evolution API.',
        )

    def handle(self, *args, **options):
        self.stdout.write(f"WHATSAPP_ENABLED: {settings.WHATSAPP_ENABLED}")
        self.stdout.write(f"EVOLUTION_API_URL: {settings.EVOLUTION_API_URL or '—'}")
        self.stdout.write(f"EVOLUTION_INSTANCE: {settings.EVOLUTION_INSTANCE or '—'}")
        self.stdout.write(f"Configured: {client.is_configured()}")

        if not settings.EVOLUTION_API_URL or not settings.EVOLUTION_API_KEY:
            self.stdout.write(self.style.ERROR(
                'أضِف EVOLUTION_API_URL و EVOLUTION_API_KEY في Environment.'
            ))
            raise SystemExit(1)

        if options.get('list_instances'):
            self._list_instances()

        send_to = (options.get('send_to') or '').strip()
        send_pdf = (options.get('send_pdf') or '').strip()
        if send_to or send_pdf:
            if not client.is_configured():
                instance = (settings.EVOLUTION_INSTANCE or '').strip()
                if instance and not client._INSTANCE_RE.fullmatch(instance):
                    self.stdout.write(self.style.ERROR(
                        f'EVOLUTION_INSTANCE="{instance}" غير صالح — استخدم اسماً إنجليزياً '
                        '(مثل hr). شغّل: python manage.py test_whatsapp --list-instances'
                    ))
                else:
                    self.stdout.write(self.style.ERROR(
                        'فعّل WHATSAPP_ENABLED=true وحدّد EVOLUTION_INSTANCE.'
                    ))
                raise SystemExit(1)
            try:
                target = send_pdf or send_to
                if send_pdf:
                    pdf_bytes = (
                        b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF'
                    )
                    result = client.send_document(
                        phone=target,
                        pdf_bytes=pdf_bytes,
                        file_name='test-operations-report.pdf',
                        caption='رسالة تجريبية — تقرير العمليات PDF',
                    )
                else:
                    result = client.send_text(
                        phone=target,
                        text='رسالة تجريبية من نظام الموارد البشرية ✓',
                    )
                self.stdout.write(self.style.SUCCESS('تم الإرسال.'))
                self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            except client.EvolutionAPIError as exc:
                self.stdout.write(self.style.ERROR(str(exc)))
                if exc.payload:
                    self.stdout.write(str(exc.payload)[:1000])
                raise SystemExit(1) from exc

    def _list_instances(self):
        url = f'{settings.EVOLUTION_API_URL.rstrip("/")}/instance/fetchInstances'
        req = urllib.request.Request(
            url,
            headers={'apikey': settings.EVOLUTION_API_KEY},
            method='GET',
        )
        try:
            with urllib.request.urlopen(req, timeout=settings.EVOLUTION_API_TIMEOUT) as resp:
                raw = resp.read().decode('utf-8')
                data = json.loads(raw) if raw else []
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            self.stdout.write(self.style.ERROR(f'HTTP {exc.code}: {detail[:500]}'))
            return
        except urllib.error.URLError as exc:
            self.stdout.write(self.style.ERROR(f'Connection error: {exc}'))
            return

        self.stdout.write(self.style.SUCCESS('Instances:'))
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get('name') or item.get('instanceName') or item.get('instance')
                    state = item.get('connectionStatus') or item.get('state') or '—'
                    self.stdout.write(f"  - {name or item} ({state})")
                else:
                    self.stdout.write(f'  - {item}')
        else:
            self.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
