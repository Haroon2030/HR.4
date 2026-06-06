"""اختبارات أمن API — تصعيد الصلاحيات ومنح أدوار حساسة."""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.core.models import AppModule, Branch, Company, Permission, Role, UserProfile

User = get_user_model()


class APIUserEscalationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='Main', code='M1', company=cls.company)

        cls.admin_role = Role.objects.create(
            name='Admin',
            role_type=Role.RoleType.ADMIN,
            is_system_role=True,
        )
        cls.specialist_role = Role.objects.create(
            name='Specialist',
            role_type=Role.RoleType.SPECIALIST,
        )
        cls.employee_role = Role.objects.create(
            name='Employee',
            role_type=Role.RoleType.EMPLOYEE,
        )

        users_mod, _ = AppModule.objects.get_or_create(
            code='users',
            defaults={'name': 'Users', 'icon': 'shield', 'order': 5},
        )
        for code, op, name in (
            ('users.edit', Permission.Operation.EDIT, 'Edit'),
            ('users.view', Permission.Operation.VIEW, 'View'),
            ('users.add', Permission.Operation.ADD, 'Add'),
        ):
            perm, _ = Permission.objects.get_or_create(
                code=code,
                defaults={'module': users_mod, 'operation': op, 'name': name},
            )
            cls.specialist_role.permissions.add(perm)

        cls.editor = User.objects.create_user(
            username='api_editor',
            password='Editor-User-99!',
        )
        ep = cls.editor.profile
        ep.role = cls.specialist_role
        ep.branch = cls.branch
        ep.save()
        ep.assigned_branches.add(cls.branch)

        cls.victim = User.objects.create_user(
            username='api_victim',
            password='Victim-User-99!',
        )
        vp = cls.victim.profile
        vp.role = cls.employee_role
        vp.branch = cls.branch
        vp.save()

    def setUp(self):
        self.client = APIClient()
        self.assertTrue(
            self.client.login(username='api_editor', password='Editor-User-99!'),
        )

    def test_patch_user_cannot_assign_admin_role(self):
        response = self.client.patch(
            f'/api/v1/users/{self.victim.pk}/',
            {'role': self.admin_role.pk},
            format='json',
        )
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST))
        self.victim.refresh_from_db()
        self.assertEqual(self.victim.profile.role_id, self.employee_role.id)

    def test_patch_self_cannot_change_own_role(self):
        response = self.client.patch(
            f'/api/v1/users/{self.editor.pk}/',
            {'role': self.admin_role.pk},
            format='json',
        )
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST))
        self.editor.refresh_from_db()
        self.assertEqual(self.editor.profile.role_id, self.specialist_role.id)

    def test_assign_permissions_blocks_sensitive_codes(self):
        custom_role = Role.objects.create(
            name='Custom',
            role_type=Role.RoleType.SPECIALIST,
        )
        users_delete, _ = Permission.objects.get_or_create(
            code='users.delete',
            defaults={
                'module': AppModule.objects.get(code='users'),
                'operation': Permission.Operation.DELETE,
                'name': 'Delete users',
            },
        )
        response = self.client.post(
            f'/api/v1/roles/{custom_role.pk}/assign_permissions/',
            {'permission_ids': [users_delete.pk]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(custom_role.permissions.filter(pk=users_delete.pk).exists())
