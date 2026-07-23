"""اختبارات أمان نظام الصلاحيات."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.core.decorators import get_user_permissions, has_permission
from apps.core.forms import RoleForm
from apps.core.models import AppModule, Branch, Company, Permission, Role, UserProfile
from apps.maintenance.sub_permissions import (
    MAINTENANCE_SCREEN_ASSIGN_VIEW,
    MAINTENANCE_SCREEN_REQUESTS_VIEW,
)

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class RoleTypeEscalationTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة اختبار')
        self.branch = Branch.objects.create(name='فرع 1', code='SEC1', company=company)
        self.manager_role = Role.objects.create(
            name='مدير فرع اختبار',
            role_type=Role.RoleType.MANAGER,
            is_system_role=False,
        )
        perm, _ = Permission.objects.get_or_create(
            code='users.manage_roles',
            defaults={'name': 'إدارة الأدوار', 'operation': 'manage_roles', 'is_active': True},
        )
        self.manager_role.permissions.add(perm)
        self.manager = User.objects.create_user(username='branch_mgr', password='pass')
        profile = self.manager.profile
        profile.role = self.manager_role
        profile.branch = self.branch
        profile.save(update_fields=['role', 'branch'])

        self.target_role = Role.objects.create(
            name='دور موظف',
            role_type=Role.RoleType.EMPLOYEE,
            is_system_role=False,
        )

    def test_non_superuser_cannot_escalate_role_type_to_admin_via_form(self):
        form = RoleForm(
            data={
                'name': self.target_role.name,
                'role_type': Role.RoleType.ADMIN,
                'description': '',
                'is_active': '1',
            },
            instance=self.target_role,
            actor=self.manager,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('role_type', form.errors)

    def test_non_privileged_cannot_grant_payroll_permission(self):
        from apps.core.services.access_control import validate_permission_grants

        err = validate_permission_grants(self.manager, ['payroll.process'])
        self.assertIsNotNone(err)
        self.assertIn('حساسة', err)

    def test_non_privileged_cannot_grant_attendance_manage(self):
        from apps.core.services.access_control import validate_permission_grants

        err = validate_permission_grants(self.manager, ['attendance.manage'])
        self.assertIsNotNone(err)

    def test_non_superuser_cannot_create_admin_role_via_form(self):
        form = RoleForm(
            data={
                'name': 'دور أدمن جديد',
                'role_type': Role.RoleType.ADMIN,
                'description': '',
                'is_active': '1',
            },
            actor=self.manager,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('role_type', form.errors)


@override_settings(ALLOWED_HOSTS=['testserver'])
class MaintenanceDeniedScreenTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة صيانة')
        self.branch = Branch.objects.create(name='فرع صيانة', code='MNT1', company=company)
        self.role = Role.objects.create(
            name='صيانة اختبار',
            role_type=Role.RoleType.EMPLOYEE,
            is_system_role=False,
        )
        self.user = User.objects.create_user(username='maint_user', password='pass')
        profile = self.user.profile
        profile.role = self.role
        profile.branch = self.branch
        profile.save(update_fields=['role', 'branch'])

        mod, _ = AppModule.objects.get_or_create(
            code='maintenance',
            defaults={'name': 'صيانة', 'icon': 'wrench', 'order': 14, 'is_active': True},
        )
        base_perm, _ = Permission.objects.get_or_create(
            code='maintenance.view',
            defaults={'name': 'عرض صيانة', 'module': mod, 'operation': 'view', 'is_active': True},
        )
        requests_mod, _ = AppModule.objects.get_or_create(
            code='maintenance_screen_requests',
            defaults={'name': 'طلبات', 'icon': 'wrench', 'order': 141, 'is_active': True},
        )
        requests_perm, _ = Permission.objects.get_or_create(
            code=MAINTENANCE_SCREEN_REQUESTS_VIEW,
            defaults={
                'name': 'طلبات صيانة',
                'module': requests_mod,
                'operation': 'view',
                'is_active': True,
            },
        )
        self.role.permissions.set([base_perm, requests_perm])
        profile.denied_permissions.set([requests_perm])
        self.user = User.objects.select_related('profile__role').get(pk=self.user.pk)

    def test_denied_maintenance_requests_screen_removed_after_expand(self):
        self.assertFalse(has_permission(self.user, MAINTENANCE_SCREEN_REQUESTS_VIEW))

    def test_denied_user_cannot_open_requests_list(self):
        client = Client()
        client.force_login(self.user)
        response = client.get('/maintenance/requests/')
        self.assertEqual(response.status_code, 302)

    def test_assign_without_requests_view_is_blocked(self):
        assign_mod, _ = AppModule.objects.get_or_create(
            code='maintenance_screen_assign',
            defaults={'name': 'إسناد', 'icon': 'wrench', 'order': 143, 'is_active': True},
        )
        assign_perm, _ = Permission.objects.get_or_create(
            code=MAINTENANCE_SCREEN_ASSIGN_VIEW,
            defaults={
                'name': 'إسناد',
                'module': assign_mod,
                'operation': 'view',
                'is_active': True,
            },
        )
        self.role.permissions.add(assign_perm)
        if hasattr(self.user, '_perm_codes_cache'):
            delattr(self.user, '_perm_codes_cache')
        self.user = User.objects.select_related('profile__role').get(pk=self.user.pk)
        self.assertTrue(has_permission(self.user, MAINTENANCE_SCREEN_ASSIGN_VIEW))
        self.assertFalse(has_permission(self.user, MAINTENANCE_SCREEN_REQUESTS_VIEW))

        client = Client()
        client.force_login(self.user)
        response = client.post('/maintenance/requests/1/assign/', {'worker_id': '1'})
        self.assertEqual(response.status_code, 302)
