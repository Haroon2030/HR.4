"""ربط موظف بجهاز البصمة: صلاحية مستقلة لأخصائي ومدير الموارد."""
import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.decorators import has_permission
from apps.core.models import Role

User = get_user_model()


class AttendanceLinkPermissionTests(TestCase):
    def _user(self, name, role_type):
        user = User.objects.create_user(name, password='x')
        role = Role.objects.create(name=f'دور {name}', role_type=role_type)
        user.profile.role = role
        user.profile.save(update_fields=['role'])
        return user

    def test_migration_grants_hr_roles_and_keeps_manage_holders(self):
        from apps.core.models import Permission
        officer = self._user('lk_officer', Role.RoleType.HR_OFFICER)
        manager = self._user('lk_manager', Role.RoleType.HR_MANAGER)
        other = self._user('lk_other', Role.RoleType.SPECIALIST)
        legacy = self._user('lk_legacy', Role.RoleType.MANAGER)
        legacy.profile.role.permissions.add(Permission.objects.get(code='attendance.manage'))
        importlib.import_module(
            'apps.core.migrations.0062_attendance_link_employee_permission'
        ).forward(django_apps, None)
        for name in ('0064_link_employee_to_devices_screen', '0065_attendance_link_screen'):
            importlib.import_module(f'apps.core.migrations.{name}').forward(django_apps, None)
        for user, expected in ((officer, True), (manager, True), (legacy, True), (other, False)):
            user = User.objects.get(pk=user.pk)
            self.assertEqual(has_permission(user, 'attendance_screen_link.view'), expected, user.username)

    def test_save_endpoint_requires_link_permission(self):
        officer = self._user('lk_officer2', Role.RoleType.SPECIALIST)
        self.client.force_login(officer)
        r = self.client.post(reverse('web:biometric_enrollment_save'), {})
        self.assertIn(r.status_code, (302, 403))
        self.assertNotEqual(r.status_code, 200)


class LinkScreenSeparateFromDevicesTests(TestCase):
    """شاشة «ربط البصمة» تُمنح وحدها دون شاشة الأجهزة."""

    def test_link_only_user_sees_link_screen_not_devices_screen(self):
        from apps.core.models import Permission
        user = User.objects.create_user('lk_only', password='x')
        role = Role.objects.create(name='دور ربط فقط', role_type=Role.RoleType.HR_OFFICER)
        role.permissions.add(Permission.objects.get(code='attendance_screen_link.view'))
        user.profile.role = role
        user.profile.save(update_fields=['role'])
        self.client.force_login(user)

        r = self.client.get(reverse('web:biometric_link'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ربط البصمة')
        self.assertNotContains(r, 'إضافة جهاز')
        self.assertNotContains(r, 'role="tablist"')

        r = self.client.get(reverse('web:biometric_devices'))
        self.assertEqual(r.status_code, 302)

    def test_devices_only_user_cannot_open_link_screen(self):
        from apps.core.models import Permission
        user = User.objects.create_user('dv_only', password='x')
        role = Role.objects.create(name='دور أجهزة فقط', role_type=Role.RoleType.HR_OFFICER)
        role.permissions.add(Permission.objects.get(code='attendance_screen_devices.view'))
        user.profile.role = role
        user.profile.save(update_fields=['role'])
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('web:biometric_link')).status_code, 302)
        self.assertEqual(self.client.get(reverse('web:biometric_devices')).status_code, 200)
