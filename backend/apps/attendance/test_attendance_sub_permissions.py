"""اختبارات صلاحيات الشاشات الفرعية للحضور والبصمة."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.core.decorators import get_user_permissions, has_permission
from apps.core.models import AppModule, Branch, Company, Permission, Role, UserProfile

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class AttendanceSubPermissionsTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة اختبار')
        self.branch = Branch.objects.create(name='فرع 1', code='TBR1', company=company)

        self.role = Role.objects.create(
            name='حضور محدود اختبار',
            role_type=Role.RoleType.EMPLOYEE,
            is_system_role=False,
        )
        self.user = User.objects.create_user(username='att_records_only', password='pass')
        profile = self.user.profile
        profile.role = self.role
        profile.branch = self.branch
        profile.save(update_fields=['role', 'branch'])

        mod, _ = AppModule.objects.get_or_create(
            code='attendance_screen_records',
            defaults={
                'name': 'الحضور — سجلات الحضور',
                'icon': 'fingerprint',
                'order': 114,
                'is_active': True,
            },
        )
        perm, _ = Permission.objects.get_or_create(
            code='attendance_screen_records.view',
            defaults={
                'name': 'الحضور — سجلات الحضور',
                'module': mod,
                'operation': 'view',
                'is_active': True,
            },
        )
        self.role.permissions.set([perm])
        self.user = User.objects.select_related('profile__role').get(pk=self.user.pk)

    def test_records_only_permission_does_not_expand_to_full_attendance(self):
        codes = get_user_permissions(self.user)
        self.assertIn('attendance_screen_records.view', codes)
        self.assertNotIn('attendance.view', codes)
        self.assertNotIn('attendance_screen_devices.view', codes)
        self.assertTrue(has_permission(self.user, 'attendance_screen_records.view'))
        self.assertFalse(has_permission(self.user, 'attendance_screen_devices.view'))

    def test_records_only_user_can_access_records_not_devices(self):
        client = Client()
        client.force_login(self.user)
        records_resp = client.get('/attendance/records/')
        devices_resp = client.get('/attendance/devices/')
        self.assertEqual(records_resp.status_code, 200, records_resp.content[:500])
        self.assertEqual(devices_resp.status_code, 302)

    def test_attendance_view_expands_to_all_screen_permissions(self):
        mod, _ = AppModule.objects.get_or_create(
            code='attendance',
            defaults={'name': 'الحضور والبصمة', 'icon': 'fingerprint', 'order': 11, 'is_active': True},
        )
        base_perm, _ = Permission.objects.get_or_create(
            code='attendance.view',
            defaults={'name': 'عرض الحضور', 'module': mod, 'operation': 'view', 'is_active': True},
        )
        full_role = Role.objects.create(
            name='حضور كامل اختبار',
            role_type=Role.RoleType.EMPLOYEE,
            is_system_role=False,
        )
        full_role.permissions.set([base_perm])
        full_user = User.objects.create_user(username='att_full', password='pass')
        UserProfile.objects.update_or_create(user=full_user, defaults={'role': full_role})
        full_user = User.objects.select_related('profile__role').get(pk=full_user.pk)

        codes = get_user_permissions(full_user)
        self.assertIn('attendance.view', codes)
        self.assertIn('attendance_screen_devices.view', codes)
        self.assertIn('attendance_screen_report.view', codes)
        self.assertIn('attendance_screen_late_alerts.view', codes)
        self.assertIn('attendance_screen_records.view', codes)

    def test_denied_attendance_screen_removed_after_expand(self):
        mod, _ = AppModule.objects.get_or_create(
            code='attendance',
            defaults={'name': 'الحضور والبصمة', 'icon': 'fingerprint', 'order': 11, 'is_active': True},
        )
        base_perm, _ = Permission.objects.get_or_create(
            code='attendance.view',
            defaults={'name': 'عرض الحضور', 'module': mod, 'operation': 'view', 'is_active': True},
        )
        devices_mod, _ = AppModule.objects.get_or_create(
            code='attendance_screen_devices',
            defaults={'name': 'أجهزة', 'icon': 'fingerprint', 'order': 111, 'is_active': True},
        )
        devices_perm, _ = Permission.objects.get_or_create(
            code='attendance_screen_devices.view',
            defaults={'name': 'أجهزة', 'module': devices_mod, 'operation': 'view', 'is_active': True},
        )
        role = Role.objects.create(
            name='حضور مع حرمان',
            role_type=Role.RoleType.HR_OFFICER,
            is_system_role=False,
        )
        role.permissions.set([base_perm, devices_perm])
        user = User.objects.create_user(username='att_denied_devices', password='pass')
        profile = user.profile
        profile.role = role
        profile.branch = self.branch
        profile.save(update_fields=['role', 'branch'])
        profile.denied_permissions.set([devices_perm])
        user = User.objects.select_related('profile__role').get(pk=user.pk)

        self.assertTrue(has_permission(user, 'attendance.view'))
        self.assertFalse(has_permission(user, 'attendance_screen_devices.view'))
