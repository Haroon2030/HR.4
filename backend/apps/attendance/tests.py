from django.test import TestCase, override_settings
from django.utils import timezone

from apps.attendance.models import AttendancePunch, BiometricDevice
from apps.attendance.services.attendance_pull import pull_device_attendance
from apps.attendance.services.zk_client import probe_device, sync_device_attendance
from apps.attendance.validators import cloud_pull_blocked_message, validate_device_ipv4


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

    def test_late_checkin_filter_hides_entry_after_grace(self):
        from datetime import datetime, time
        from apps.attendance.models import EmployeeBiometricEnrollment, EmployeeBiometricSettings
        from apps.attendance.services.employee_punch_display import apply_late_checkin_filter
        from apps.core.models import Branch, Company
        from apps.employees.models import Employee

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        device = BiometricDevice.objects.create(name='جهاز', ip_address='192.168.1.50', port=4370, branch=branch)
        emp = Employee.objects.create(name='موظف', branch=branch)
        EmployeeBiometricEnrollment.objects.create(employee=emp, device=device, device_user_id=7)
        settings = EmployeeBiometricSettings.objects.create(
            employee=emp, expected_check_in=time(8, 0), late_grace_minutes=30,
        )
        tz = timezone.get_current_timezone()
        day = timezone.localdate()
        early = timezone.make_aware(datetime.combine(day, time(8, 15)), tz)
        late = timezone.make_aware(datetime.combine(day, time(9, 0)), tz)
        p1 = AttendancePunch.objects.create(
            device=device, employee=emp, device_user_id=7,
            punched_at=early, punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        p2 = AttendancePunch.objects.create(
            device=device, employee=emp, device_user_id=7,
            punched_at=late, punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        visible, hidden = apply_late_checkin_filter([p2, p1], settings)
        self.assertEqual(hidden, 1)
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].id, p1.id)

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

    def test_cloud_pull_blocked_on_lan(self):
        device = BiometricDevice.objects.create(
            name='LAN', ip_address='192.168.1.10', port=4370,
        )
        msg = cloud_pull_blocked_message(device, force_mock=False)
        self.assertIsNotNone(msg)
        self.assertIn('agent.py', msg)
