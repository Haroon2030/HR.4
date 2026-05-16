"""
تعبئة الحقول المعروضة لسجلات الحضور (أسماء + تسميات التحقق).

python manage.py backfill_attendance_fields
"""
from django.core.management.base import BaseCommand
from apps.attendance.models import AttendancePunch, BiometricDeviceUser
from apps.attendance.services.labels import punch_type_for_status, verify_mode_label


class Command(BaseCommand):
    help = 'تحديث device_user_name و verify_mode_label و punch_type من البيانات الخام'

    def add_arguments(self, parser):
        parser.add_argument('--device', type=int, help='معرّف جهاز محدد')

    def handle(self, *args, **options):
        qs = AttendancePunch.objects.filter(is_deleted=False)
        if options.get('device'):
            qs = qs.filter(device_id=options['device'])

        name_maps: dict[int, dict[int, str]] = {}
        updated = 0
        for punch in qs.iterator(chunk_size=500):
            device_id = punch.device_id
            if device_id not in name_maps:
                name_maps[device_id] = {
                    u.device_user_id: u.name
                    for u in BiometricDeviceUser.objects.filter(
                        device_id=device_id, is_deleted=False,
                    )
                }
            nm = name_maps[device_id]
            fields = []
            if not punch.device_user_name and nm.get(punch.device_user_id):
                punch.device_user_name = nm[punch.device_user_id]
                fields.append('device_user_name')
            if punch.raw_status is not None:
                code, _ = punch_type_for_status(punch.raw_status)
                if code in {c.value for c in AttendancePunch.PunchType} and punch.punch_type != code:
                    punch.punch_type = code
                    fields.append('punch_type')
            label = verify_mode_label(punch.verify_mode)
            if punch.verify_mode_label != label:
                punch.verify_mode_label = label
                fields.append('verify_mode_label')
            if fields:
                fields.append('updated_at')
                punch.save(update_fields=fields)
                updated += 1

        self.stdout.write(self.style.SUCCESS(f'تم تحديث {updated} سجل.'))
