"""مسح الأجهزة المحذوفة منطقياً نهائياً من PostgreSQL (تنظيف بعد الترقية)."""
from django.core.management.base import BaseCommand

from apps.attendance.services.device_purge import purge_soft_deleted_biometric_devices


class Command(BaseCommand):
    help = 'حذف نهائي لكل أجهزة البصمة ذات is_deleted=True (مع البصمات المرتبطة)'

    def handle(self, *args, **options):
        rows = purge_soft_deleted_biometric_devices()
        if not rows:
            self.stdout.write(self.style.SUCCESS('لا توجد أجهزة محذوفة منطقياً.'))
            return
        for row in rows:
            self.stdout.write(
                f'  جهاز {row["device_id"]} «{row["name"]}»: '
                f'{row["punches"]} بصمة، {row["device_users"]} مستخدم، {row["enrollments"]} ربط'
            )
        self.stdout.write(self.style.SUCCESS(f'تم مسح {len(rows)} جهازاً نهائياً.'))
