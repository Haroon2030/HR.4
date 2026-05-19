"""تفريغ جدول سجلات البصمة (attendance_attendancepunch) للبدء من جديد."""
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.attendance.models import AttendancePunch


class Command(BaseCommand):
    help = (
        'حذف نهائي لكل صفوف attendance_attendancepunch. '
        'مثال: python manage.py clear_attendance_punches --yes'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--device',
            type=int,
            help='تفريغ سجلات جهاز واحد فقط',
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            help='تأكيد الحذف النهائي (لا يمكن التراجع)',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            self.stderr.write(
                self.style.ERROR(
                    'عملية خطيرة: سيُحذف كل محتوى جدول سجلات البصمة.\n'
                    'للتنفيذ أضف: --yes'
                )
            )
            return

        qs = AttendancePunch.all_objects.all()
        if options.get('device'):
            qs = qs.filter(device_id=options['device'])
            scope = f'جهاز {options["device"]}'
        else:
            scope = 'كل الأجهزة'

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS(f'لا توجد سجلات للحذف ({scope}).'))
            return

        with transaction.atomic():
            deleted, _ = qs.hard_delete()
            self._reset_id_sequence()

        self.stdout.write(
            self.style.SUCCESS(
                f'تم تفريغ جدول سجلات البصمة ({scope}): حُذف {deleted} سجل (كان {total}).'
            )
        )

    def _reset_id_sequence(self) -> None:
        if connection.vendor != 'postgresql':
            return
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence('attendance_attendancepunch', 'id'),
                    1,
                    false
                )
                """
            )
