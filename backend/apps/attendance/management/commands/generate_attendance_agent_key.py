"""إنشاء مفتاح وكيل بصمة — عام (.env) أو لجهاز محدد."""
import secrets

from django.core.management.base import BaseCommand, CommandError

from apps.attendance.models import BiometricDevice
from apps.attendance.services.agent_keys import set_device_agent_key


class Command(BaseCommand):
    help = (
        'يولّد مفتاح ATTENDANCE_AGENT_API_KEY للـ .env، '
        'أو مفتاحاً لجهاز بصمة (--device-id)'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--device-id',
            type=int,
            help='معرّف جهاز البصمة — يُخزَّن مُجزّأاً في قاعدة البيانات',
        )

    def handle(self, *args, **options):
        device_id = options.get('device_id')
        if device_id:
            device = BiometricDevice.objects.filter(pk=device_id, is_deleted=False).first()
            if not device:
                raise CommandError(f'الجهاز {device_id} غير موجود.')
            raw = set_device_agent_key(device)
            self.stdout.write(self.style.SUCCESS(
                f'مفتاح جهاز «{device.name}» (id={device.pk}) — احفظه في الوكيل المحلي:'
            ))
            self.stdout.write(raw)
            self.stdout.write(self.style.WARNING(
                'لن يُعرض المفتاح مرة أخرى. استخدم Header: X-Attendance-Agent-Key'
            ))
            return

        key = secrets.token_urlsafe(48)
        self.stdout.write(self.style.SUCCESS('أضف السطر التالي إلى .env على السيرفر (مفتاح عام):'))
        self.stdout.write(f'ATTENDANCE_AGENT_API_KEY={key}')
