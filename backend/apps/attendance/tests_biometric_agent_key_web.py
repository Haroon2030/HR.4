"""اختبارات توليد مفتاح وكيل البصمة من واجهة الويب."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.attendance.models import BiometricDevice
from apps.attendance.services.agent_keys import hash_agent_key, verify_agent_key
from apps.core.models import AppModule, Branch, Company, Permission, Role

User = get_user_model()


def _attendance_perms():
    mod, _ = AppModule.objects.get_or_create(
        code='attendance',
        defaults={'name': 'الحضور', 'icon': 'fingerprint', 'order': 11},
    )
    perms = []
    for code, op, name in (
        ('attendance.view', Permission.Operation.VIEW, 'عرض'),
        ('attendance.manage', Permission.Operation.EDIT, 'إدارة'),
    ):
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={'module': mod, 'operation': op, 'name': name},
        )
        perms.append(perm)
    return perms


class BiometricAgentKeyWebTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='Co')
        branch = Branch.objects.create(company=company, name='فرع', code='BR1')
        self.device = BiometricDevice.objects.create(
            name='جهاز اختبار',
            ip_address='192.168.1.10',
            port=4370,
            branch=branch,
        )
        view_perm, manage_perm = _attendance_perms()
        role = Role.objects.create(name='مدير بصمة', role_type=Role.RoleType.SPECIALIST)
        role.permissions.add(manage_perm, view_perm)

        self.user = User.objects.create_user(username='bio_admin', password='test-pass-123')
        profile = self.user.profile
        profile.role = role
        profile.branch = branch
        profile.save()

        self.client = Client()
        self.client.login(username='bio_admin', password='test-pass-123')

    def test_generate_agent_key_returns_json(self):
        response = self.client.post(
            f'/attendance/devices/{self.device.pk}/agent-key/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['api_key'])
        self.assertEqual(data['device_id'], self.device.pk)

        self.device.refresh_from_db()
        self.assertTrue(verify_agent_key(self.device, data['api_key']))
        self.assertEqual(self.device.agent_api_key, hash_agent_key(data['api_key']))

    def test_regenerate_replaces_old_key(self):
        first = self.client.post(
            f'/attendance/devices/{self.device.pk}/agent-key/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        ).json()['api_key']
        second = self.client.post(
            f'/attendance/devices/{self.device.pk}/agent-key/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        ).json()['api_key']
        self.assertNotEqual(first, second)
        self.device.refresh_from_db()
        self.assertTrue(verify_agent_key(self.device, second))
        self.assertFalse(verify_agent_key(self.device, first))

    def test_requires_manage_permission(self):
        view_perm, _ = _attendance_perms()
        viewer_role = Role.objects.create(name='عارض بصمة', role_type=Role.RoleType.EMPLOYEE)
        viewer_role.permissions.add(view_perm)
        viewer = User.objects.create_user(username='viewer', password='test-pass-123')
        vp = viewer.profile
        vp.role = viewer_role
        vp.save()

        client = Client()
        client.login(username='viewer', password='test-pass-123')
        response = client.post(f'/attendance/devices/{self.device.pk}/agent-key/')
        self.assertIn(response.status_code, (302, 403))
