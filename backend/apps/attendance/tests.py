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

    def test_punches_only_from_enrolled_device_pair(self):
        from datetime import datetime, time

        from apps.attendance.models import EmployeeBiometricEnrollment
        from apps.attendance.services.employee_punch_display import base_punches_queryset
        from apps.core.models import Branch, Company
        from apps.employees.models import Employee

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        sky = BiometricDevice.objects.create(
            name='سكاي مول', ip_address='192.168.51.3', port=4370, branch=branch,
        )
        waha = BiometricDevice.objects.create(
            name='الواحة', ip_address='192.168.24.59', port=4370, branch=branch,
        )
        emp = Employee.objects.create(name='هارون', branch=branch)
        EmployeeBiometricEnrollment.objects.create(
            employee=emp, device=sky, device_user_id=1,
        )
        tz = timezone.get_current_timezone()
        day = timezone.localdate()
        ts_sky = timezone.make_aware(datetime.combine(day, time(14, 29)), tz)
        ts_waha = timezone.make_aware(datetime.combine(day, time(9, 0)), tz)
        AttendancePunch.objects.create(
            device=sky, employee=emp, device_user_id=1,
            punched_at=ts_sky, punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        AttendancePunch.objects.create(
            device=waha, employee=emp, device_user_id=99,
            punched_at=ts_waha, punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        ids = set(base_punches_queryset(emp).values_list('device_id', flat=True))
        self.assertEqual(ids, {sky.id})

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

    def test_incremental_skips_older_than_watermark(self):
        from datetime import timedelta

        from apps.attendance.services.attendance_pull import EnrichedPunch
        from apps.attendance.services.punch_sync import import_enriched_punches

        device = BiometricDevice.objects.create(
            name='incr-test', ip_address='10.0.0.11', port=4370,
        )
        wm_ts = (timezone.now() - timedelta(hours=1)).replace(microsecond=0)
        old_ts = (timezone.now() - timedelta(days=1)).replace(microsecond=0)
        new_ts = timezone.now().replace(microsecond=0)
        AttendancePunch.objects.create(
            device=device,
            device_user_id=1,
            punched_at=wm_ts,
            punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        outcome = import_enriched_punches(
            device,
            [
                EnrichedPunch(
                    device_user_id=1,
                    device_user_name='a',
                    punched_at=old_ts,
                    punch_type='in',
                    punch_type_label='دخول',
                    verify_mode=1,
                    verify_mode_label='بصمة',
                    device_record_uid=None,
                    raw_status=0,
                ),
                EnrichedPunch(
                    device_user_id=2,
                    device_user_name='b',
                    punched_at=new_ts,
                    punch_type='in',
                    punch_type_label='دخول',
                    verify_mode=1,
                    verify_mode_label='بصمة',
                    device_record_uid=None,
                    raw_status=0,
                ),
            ],
            dry_run=False,
            incremental=True,
        )
        self.assertEqual(outcome['imported'], 1)
        self.assertGreaterEqual(outcome['skipped_time_filter'], 1)
        self.assertEqual(AttendancePunch.objects.filter(device=device).count(), 2)


class LinkedEnrollmentDisplayTests(TestCase):
    """عرض بصمات الموظفين المربوطين حتى بدون employee_id على السجل."""

    def test_mapped_filter_includes_enrollment_without_employee_id(self):
        from apps.attendance.models import EmployeeBiometricEnrollment
        from apps.attendance.selectors.punch_records import get_punch_queryset
        from apps.core.models import Branch, Company
        from apps.employees.models import Employee

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        device = BiometricDevice.objects.create(
            name='جهاز', ip_address='192.168.1.60', port=4370, branch=branch,
        )
        emp = Employee.objects.create(name='مربوط', branch=branch)
        EmployeeBiometricEnrollment.objects.create(
            employee=emp, device=device, device_user_id=5,
        )
        AttendancePunch.objects.create(
            device=device,
            employee=None,
            device_user_id=5,
            punched_at=timezone.now(),
            punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        mapped = get_punch_queryset(mapped_only=True)
        self.assertEqual(mapped.count(), 1)

    def test_daily_report_groups_enrolled_employee(self):
        from datetime import datetime, time

        from apps.attendance.models import EmployeeBiometricEnrollment
        from apps.attendance.selectors.daily_report import build_daily_attendance_rows
        from apps.attendance.selectors.punch_records import get_punch_queryset
        from apps.core.models import Branch, Company
        from apps.employees.models import Employee

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        device = BiometricDevice.objects.create(
            name='جهاز', ip_address='192.168.1.61', port=4370, branch=branch,
        )
        emp = Employee.objects.create(name='هارون', employee_number='E1', branch=branch)
        EmployeeBiometricEnrollment.objects.create(
            employee=emp, device=device, device_user_id=1,
        )
        tz = timezone.get_current_timezone()
        day = timezone.localdate()
        ts = timezone.make_aware(datetime.combine(day, time(9, 0)), tz)
        AttendancePunch.objects.create(
            device=device,
            employee=None,
            device_user_id=1,
            punched_at=ts,
            punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        qs = get_punch_queryset()
        rows = build_daily_attendance_rows(qs)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].is_mapped)
        self.assertEqual(rows[0].employee_name, 'هارون')
        self.assertEqual(rows[0].status_label, 'بصمة واحدة')

    def test_late_checkin_alerts_from_biometric_settings(self):
        from datetime import datetime, time

        from django.contrib.auth import get_user_model

        from apps.attendance.models import EmployeeBiometricEnrollment, EmployeeBiometricSettings
        from apps.attendance.selectors.late_alerts import build_late_checkin_alerts, summarize_late_alerts
        from apps.core.models import Branch, Company
        from apps.employees.models import Employee

        User = get_user_model()
        user = User.objects.create_superuser(username='late_admin', password='x')

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        device = BiometricDevice.objects.create(
            name='جهاز', ip_address='192.168.1.62', port=4370, branch=branch,
        )
        emp = Employee.objects.create(name='متأخر', employee_number='L1', branch=branch)
        EmployeeBiometricEnrollment.objects.create(
            employee=emp, device=device, device_user_id=2,
        )
        EmployeeBiometricSettings.objects.create(
            employee=emp,
            expected_check_in=time(8, 0),
            late_grace_minutes=30,
        )
        tz = timezone.get_current_timezone()
        day = timezone.localdate()
        late = timezone.make_aware(datetime.combine(day, time(9, 0)), tz)
        AttendancePunch.objects.create(
            device=device,
            employee=emp,
            device_user_id=2,
            punched_at=late,
            punch_type=AttendancePunch.PunchType.CHECK_IN,
        )

        filters = {
            'date_from': day.isoformat(),
            'date_to': day.isoformat(),
        }
        alerts = build_late_checkin_alerts(user, filters)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].employee_id, emp.pk)
        self.assertEqual(alerts[0].late_minutes, 60)
        self.assertEqual(alerts[0].late_after_grace_minutes, 30)
        self.assertEqual(alerts[0].grace_minutes, 30)

        summary = summarize_late_alerts(alerts)
        self.assertEqual(summary['total'], 1)
        self.assertEqual(summary['employees'], 1)
        self.assertEqual(summary['max_late_minutes'], 60)

    def test_late_checkin_alerts_skips_on_time_and_missing_settings(self):
        from datetime import datetime, time

        from django.contrib.auth import get_user_model

        from apps.attendance.models import EmployeeBiometricEnrollment
        from apps.attendance.selectors.late_alerts import build_late_checkin_alerts
        from apps.core.models import Branch, Company
        from apps.employees.models import Employee

        User = get_user_model()
        user = User.objects.create_superuser(username='late_admin2', password='x')

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        device = BiometricDevice.objects.create(
            name='جهاز', ip_address='192.168.1.63', port=4370, branch=branch,
        )
        emp_no_settings = Employee.objects.create(name='بدون إعداد', branch=branch)
        emp_on_time = Employee.objects.create(name='في الوقت', branch=branch)
        EmployeeBiometricEnrollment.objects.create(
            employee=emp_no_settings, device=device, device_user_id=3,
        )
        EmployeeBiometricEnrollment.objects.create(
            employee=emp_on_time, device=device, device_user_id=4,
        )
        from apps.attendance.models import EmployeeBiometricSettings
        EmployeeBiometricSettings.objects.create(
            employee=emp_on_time,
            expected_check_in=time(8, 0),
            late_grace_minutes=30,
        )
        tz = timezone.get_current_timezone()
        day = timezone.localdate()
        late_no_settings = timezone.make_aware(datetime.combine(day, time(10, 0)), tz)
        on_time = timezone.make_aware(datetime.combine(day, time(8, 20)), tz)
        AttendancePunch.objects.create(
            device=device, employee=emp_no_settings, device_user_id=3,
            punched_at=late_no_settings, punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        AttendancePunch.objects.create(
            device=device, employee=emp_on_time, device_user_id=4,
            punched_at=on_time, punch_type=AttendancePunch.PunchType.CHECK_IN,
        )

        filters = {'date_from': day.isoformat(), 'date_to': day.isoformat()}
        alerts = build_late_checkin_alerts(user, filters)
        self.assertEqual(alerts, [])


class EmployeeFingerprintTabTests(TestCase):
    """تبويب البصمة في ملف الموظف — ربط رسمي أو مستنتج من السجلات."""

    def test_fingerprint_tab_linked_with_enrollment(self):
        from apps.attendance.models import EmployeeBiometricEnrollment
        from apps.core.models import Branch, Company
        from apps.employees.models import Employee
        from apps.employees.services.employee_view_data import load_employee_view_context

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        device = BiometricDevice.objects.create(
            name='جهاز', ip_address='192.168.1.70', port=4370, branch=branch,
        )
        emp = Employee.objects.create(name='هارون', branch=branch)
        EmployeeBiometricEnrollment.objects.create(
            employee=emp, device=device, device_user_id=9,
        )

        ctx = load_employee_view_context(
            employee=emp,
            user=None,
            active_tab='fingerprint',
            tab_visible={'fingerprint': True},
            request_get={},
            load_all_tabs=False,
        )
        fp = ctx['fingerprint_data']
        self.assertTrue(fp['linked'])
        self.assertTrue(fp['has_formal_enrollment'])
        self.assertEqual(len(fp['enrollments']), 1)

    def test_fingerprint_tab_inferred_from_punches_without_enrollment(self):
        from datetime import datetime, time

        from apps.core.models import Branch, Company
        from apps.employees.models import Employee
        from apps.employees.services.employee_view_data import load_employee_view_context

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        device = BiometricDevice.objects.create(
            name='جهاز', ip_address='192.168.1.71', port=4370, branch=branch,
        )
        emp = Employee.objects.create(name='هارون', branch=branch)
        tz = timezone.get_current_timezone()
        ts = timezone.make_aware(datetime.combine(timezone.localdate(), time(8, 0)), tz)
        AttendancePunch.objects.create(
            device=device,
            employee=emp,
            device_user_id=3,
            punched_at=ts,
            punch_type=AttendancePunch.PunchType.CHECK_IN,
        )

        ctx = load_employee_view_context(
            employee=emp,
            user=None,
            active_tab='fingerprint',
            tab_visible={'fingerprint': True},
            request_get={},
            load_all_tabs=False,
        )
        fp = ctx['fingerprint_data']
        self.assertTrue(fp['linked'])
        self.assertFalse(fp['has_formal_enrollment'])
        self.assertEqual(len(fp['enrollments']), 1)
        self.assertEqual(fp['displayed_count'], 1)

    def test_enrollment_save_restores_soft_deleted_link(self):
        from django.contrib.auth import get_user_model
        from django.test import Client

        from apps.attendance.models import EmployeeBiometricEnrollment
        from apps.core.models import Branch, Company
        from apps.employees.models import Employee

        User = get_user_model()
        user = User.objects.create_superuser(username='bio_admin', password='x')

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        device = BiometricDevice.objects.create(
            name='جهاز', ip_address='192.168.1.72', port=4370, branch=branch,
        )
        emp = Employee.objects.create(name='هارون', branch=branch)
        enrollment = EmployeeBiometricEnrollment.objects.create(
            employee=emp, device=device, device_user_id=11,
        )
        enrollment.delete()

        client = Client()
        client.force_login(user)
        response = client.post(
            '/attendance/enrollments/save/',
            {
                'employee_id': emp.pk,
                'device_id': device.pk,
                'device_user_id': 11,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            EmployeeBiometricEnrollment.objects.filter(
                employee=emp, device=device, device_user_id=11,
            ).exists()
        )


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
