from django.test import TestCase, override_settings
from django.utils import timezone

from apps.attendance.models import AttendancePunch, BiometricDevice
from apps.attendance.services.attendance_pull import pull_device_attendance
from apps.attendance.services.zk_client import probe_device, sync_device_attendance
from apps.attendance.validators import validate_device_ipv4


@override_settings(BIOMETRIC_MOCK_MODE=True)
class BiometricMockTests(TestCase):
    def test_probe_and_sync_mock(self):
        device = BiometricDevice.objects.create(
            name='جهاز تجريبي',
            ip_address='192.168.1.100',
            port=4370,
        )
        result = probe_device(device)
        self.assertTrue(result.ok)

        outcome = sync_device_attendance(device)
        self.assertTrue(outcome['ok'])
        self.assertGreaterEqual(outcome['imported'], 1)
        self.assertEqual(AttendancePunch.objects.filter(device=device).count(), outcome['imported'])

        outcome2 = sync_device_attendance(device)
        self.assertTrue(outcome2['ok'])
        self.assertEqual(outcome2['imported'], 0)
        self.assertGreater(outcome2['skipped'], 0)

    def test_pull_command_service(self):
        device = BiometricDevice.objects.create(
            name='pull-test', ip_address='10.0.0.9', port=4370,
        )
        result = pull_device_attendance(device, import_db=True, force_mock=True)
        self.assertTrue(result.ok)
        self.assertGreater(result.punches_after_filter, 0)
        self.assertGreater(AttendancePunch.objects.filter(device=device).count(), 0)

        count_after_first = AttendancePunch.objects.filter(device=device).count()
        result2 = pull_device_attendance(device, import_db=True, force_mock=True)
        self.assertTrue(result2.ok)
        self.assertEqual(result2.imported, 0)
        self.assertEqual(
            AttendancePunch.objects.filter(device=device).count(),
            count_after_first,
        )

    def test_duplicate_without_device_uid(self):
        from apps.attendance.services.punch_sync import import_enriched_punches
        from apps.attendance.services.attendance_pull import EnrichedPunch

        device = BiometricDevice.objects.create(
            name='dedup-test', ip_address='10.0.0.10', port=4370,
        )
        ts = timezone.now().replace(microsecond=0)
        punch = EnrichedPunch(
            device_user_id=7,
            device_user_name='test',
            punched_at=ts,
            punch_type='in',
            punch_type_label='دخول',
            verify_mode=1,
            verify_mode_label='بصمة',
            device_record_uid=None,
            raw_status=0,
        )
        first = import_enriched_punches(device, [punch], dry_run=False, incremental=False)
        self.assertEqual(first['imported'], 1)
        second = import_enriched_punches(device, [punch], dry_run=False, incremental=False)
        self.assertEqual(second['imported'], 0)
        self.assertEqual(AttendancePunch.objects.filter(device=device).count(), 1)


class DeviceIpValidatorTests(TestCase):
    def test_valid_ipv4(self):
        self.assertEqual(validate_device_ipv4('192.168.24.59'), '192.168.24.59')

    def test_rejects_partial_ip(self):
        with self.assertRaises(ValueError):
            validate_device_ipv4('40')
