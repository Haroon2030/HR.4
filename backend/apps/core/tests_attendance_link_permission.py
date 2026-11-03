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
        for user, expected in ((officer, True), (manager, True), (legacy, True), (other, False)):
            user = User.objects.get(pk=user.pk)
            self.assertEqual(has_permission(user, 'attendance.link_employee'), expected, user.username)

    def test_save_endpoint_requires_link_permission(self):
        officer = self._user('lk_officer2', Role.RoleType.SPECIALIST)
        self.client.force_login(officer)
        r = self.client.post(reverse('web:biometric_enrollment_save'), {})
        self.assertIn(r.status_code, (302, 403))
        self.assertNotEqual(r.status_code, 200)
