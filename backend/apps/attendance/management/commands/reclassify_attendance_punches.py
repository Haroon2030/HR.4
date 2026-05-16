"""
إعادة تصنيف دخول/خروج حسب تسلسل البصمات (لأجهزة uFace التي ترسل status=1 دائماً).

python manage.py reclassify_attendance_punches
python manage.py reclassify_attendance_punches --dry-run
python manage.py reclassify_attendance_punches --device 1
"""
from django.core.management.base import BaseCommand

from apps.attendance.services.punch_inference import device_status_health, reclassify_punches_by_sequence


class Command(BaseCommand):
    help = 'إعادة تصنيف دخول/خروج من تسلسل البصمات اليومية'

    def add_arguments(self, parser):
        parser.add_argument('--device', type=int, help='معرّف جهاز')
        parser.add_argument('--dry-run', action='store_true', help='معاينة بدون حفظ')

    def handle(self, *args, **options):
        device_id = options.get('device')
        health = device_status_health(device_id)
        self.stdout.write(
            f"تحليل status: إجمالي {health['total']} | "
            f"status=0: {health['status_0']} | status=1: {health['status_1']}"
        )
        if health['skewed']:
            self.stdout.write(self.style.WARNING(
                '⚠ الجهاز يرسل غالباً status واحد — يُنصح بإعادة التصنيف بالتسلسل.'
            ))

        result = reclassify_punches_by_sequence(
            device_id=device_id,
            dry_run=options['dry_run'],
        )
        prefix = '[معاينة] ' if result['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}دخول: {result['inferred_in']} | خروج: {result['inferred_out']} | "
            f"تم تحديث {result['updated']} سجل"
        ))
