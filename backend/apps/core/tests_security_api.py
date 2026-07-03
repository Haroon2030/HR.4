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

    def test_create_role_cannot_set_system_role(self):
        response = self.client.post(
            '/api/v1/roles/',
            {
                'name': 'Fake System',
                'role_type': Role.RoleType.SPECIALIST,
                'is_system_role': True,
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        role_id = response.json()['id']
        created = Role.objects.get(pk=role_id)
        self.assertFalse(created.is_system_role)

    def test_company_is_deleted_readonly_via_api(self):
        response = self.client.patch(
            f'/api/v1/companies/{self.company.pk}/',
            {'is_deleted': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_deleted)


class BranchEmployeesAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.employees.models import Employee

        cls.company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='Main', code='M1', company=cls.company)
        cls.role = Role.objects.create(name='Admin', role_type=Role.RoleType.ADMIN)
        branches_mod, _ = AppModule.objects.get_or_create(
            code='branches',
            defaults={'name': 'Branches', 'icon': 'building', 'order': 2},
        )
        perm, _ = Permission.objects.get_or_create(
            code='branches.view',
            defaults={
                'module': branches_mod,
                'operation': Permission.Operation.VIEW,
                'name': 'View branches',
            },
        )
        cls.role.permissions.add(perm)
        cls.user = User.objects.create_user(username='branch_api', password='Branch-Api-99!')
        profile = cls.user.profile
        profile.role = cls.role
        profile.save()
        cls.hr_employee = Employee.objects.create(
            name='موظف HR',
            employee_number='E-100',
            branch=cls.branch,
        )

    def setUp(self):
        self.client = APIClient()
        self.assertTrue(self.client.login(username='branch_api', password='Branch-Api-99!'))

    def test_branch_employees_returns_hr_records_not_user_profiles(self):
        response = self.client.get(f'/api/v1/branches/{self.branch.pk}/employees/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'موظف HR')
        self.assertEqual(data[0]['employee_number'], 'E-100')
        self.assertNotIn('username', data[0])
