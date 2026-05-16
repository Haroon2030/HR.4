"""إنشاء مفتاح وكيل بصمة عشوائي."""
import secrets

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'يولّد مفتاح ATTENDANCE_AGENT_API_KEY لوضعه في .env الإنتاج والوكيل المحلي'

    def handle(self, *args, **options):
        key = secrets.token_urlsafe(48)
        self.stdout.write(self.style.SUCCESS('أضف السطر التالي إلى .env على السيرفر والوكيل:'))
        self.stdout.write(f'ATTENDANCE_AGENT_API_KEY={key}')
