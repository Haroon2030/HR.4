"""Security regression tests — RBAC hardening."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import AppModule, Branch, Company, Permission, Role, UserProfile

User = get_user_model()


class UserAdminSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='Main', code='M1', company=cls.company)

        cls.admin_role = Role.objects.create(
            name='Admin',
            role_type=Role.RoleType.ADMIN,
            is_system_role=True,
        )
        cls.hr_mgr_role = Role.objects.create(
            name='HR Mgr',
            role_type=Role.RoleType.HR_MANAGER,
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
        cls.users_edit, _ = Permission.objects.get_or_create(
            code='users.edit',
            defaults={
                'module': users_mod,
                'operation': Permission.Operation.EDIT,
                'name': 'Edit users',
            },
        )
        cls.users_view, _ = Permission.objects.get_or_create(
            code='users.view',
            defaults={
                'module': users_mod,
                'operation': Permission.Operation.VIEW,
                'name': 'View users',
            },
        )
        cls.specialist_role.permissions.add(cls.users_edit, cls.users_view)

        cls.privileged = User.objects.create_user(
            username='protected_user',
            password='Protected-User-99!',
        )
        prof = cls.privileged.profile
        prof.role = cls.admin_role
        prof.branch = cls.branch
        prof.is_protected = True
        prof.save()

        cls.editor = User.objects.create_user(
            username='specialist_editor',
            password='Editor-User-99!',
        )
        ep = cls.editor.profile
        ep.role = cls.specialist_role
        ep.branch = cls.branch
        ep.save()
        ep.assigned_branches.add(cls.branch)

        cls.victim = User.objects.create_user(
            username='victim_user',
            password='Victim-User-99!',
        )
        vp = cls.victim.profile
        vp.role = cls.employee_role
        vp.branch = cls.branch
        vp.save()

    def setUp(self):
        self.client = Client()

    def test_protected_user_edit_blocked_for_non_superuser(self):
        self.client.login(username='specialist_editor', password='Editor-User-99!')
        url = reverse('web:edit_user', kwargs={'user_id': self.privileged.id})
        response = self.client.post(url, {
            'username': 'protected_user',
            'first_name': 'X',
            'last_name': 'Y',
            'email': '',
            'is_active': 'on',
            'role': self.employee_role.id,
            'branch': self.branch.id,
        })
        self.assertEqual(response.status_code, 302)
        self.privileged.refresh_from_db()
        self.assertEqual(self.privileged.profile.role_id, self.admin_role.id)

    def test_specialist_cannot_assign_admin_role(self):
        self.client.login(username='specialist_editor', password='Editor-User-99!')
        url = reverse('web:edit_user', kwargs={'user_id': self.victim.id})
        response = self.client.post(url, {
            'username': 'victim_user',
            'first_name': '',
            'last_name': '',
            'email': '',
            'is_active': 'on',
            'role': self.admin_role.id,
            'branch': self.branch.id,
        })
        self.assertEqual(response.status_code, 302)
        self.victim.refresh_from_db()
        self.assertEqual(self.victim.profile.role_id, self.employee_role.id)

    def test_manage_permissions_requires_privileged_actor(self):
        self.client.login(username='specialist_editor', password='Editor-User-99!')
        url = reverse('web:manage_user_permissions', kwargs={'user_id': self.victim.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('web:list_users'), response.url)

    def test_logout_requires_post(self):
        self.client.login(username='specialist_editor', password='Editor-User-99!')
        get_resp = self.client.get(reverse('web:auth:logout'))
        self.assertEqual(get_resp.status_code, 302)
        self.assertNotIn(reverse('web:auth:login'), get_resp.url)
        self.assertTrue(self.client.session.get('_auth_user_id'))

        post_resp = self.client.post(reverse('web:auth:logout'))
        self.assertEqual(post_resp.status_code, 302)
        self.assertEqual(post_resp.url, reverse('web:auth:login'))


class BranchScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch_a = Branch.objects.create(name='A', code='A1', company=cls.company)
        cls.branch_b = Branch.objects.create(name='B', code='B1', company=cls.company)

        branches_mod, _ = AppModule.objects.get_or_create(
            code='branches',
            defaults={'name': 'Branches', 'icon': 'building', 'order': 2},
        )
        view_perm, _ = Permission.objects.get_or_create(
            code='branches.view',
            defaults={
                'module': branches_mod,
                'operation': Permission.Operation.VIEW,
                'name': 'View branches',
            },
        )
        cls.role = Role.objects.create(name='Spec', role_type=Role.RoleType.SPECIALIST)
        cls.role.permissions.add(view_perm)

        cls.user = User.objects.create_user(username='scoped', password='Scoped-User-99!')
        p = cls.user.profile
        p.role = cls.role
        p.branch = cls.branch_a
        p.save()
        p.assigned_branches.add(cls.branch_a)

    def setUp(self):
        self.client = Client()

    def test_view_branch_denied_outside_scope(self):
        self.client.login(username='scoped', password='Scoped-User-99!')
        url = reverse('web:view_branch', kwargs={'branch_id': self.branch_b.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('web:list_branches'), response.url)


class WorkflowPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Co2', tax_number='2', commercial_record='2')
        cls.branch = Branch.objects.create(name='Main2', code='M2', company=cls.company)

        ops_mod, _ = AppModule.objects.get_or_create(
            code='operations',
            defaults={'name': 'Operations', 'icon': 'list', 'order': 12},
        )
        Permission.objects.get_or_create(
            code='operations.approve_branch',
            defaults={
                'module': ops_mod,
                'operation': Permission.Operation.APPROVE_BRANCH,
                'name': 'Branch approve',
            },
        )

        cls.manager = User.objects.create_user(username='bmgr2', password='Branch-Mgr-99!')
        cls.branch.manager = cls.manager
        cls.branch.save(update_fields=['manager'])

        cls.specialist = User.objects.create_user(username='spec2', password='Spec-User-99!')

    def setUp(self):
        self.client = Client()

    def test_manager_without_approve_branch_blocked(self):
        self.client.login(username='bmgr2', password='Branch-Mgr-99!')
        from apps.core.models import PendingAction
        from apps.employees.models import Employee

        employee = Employee.objects.create(name='E1', branch=self.branch)
        action = PendingAction.objects.create(
            action_type=PendingAction.ActionType.LEAVE,
            employee=employee,
            branch=self.branch,
            requested_by=self.specialist,
            status=PendingAction.Status.PENDING_BRANCH,
        )
        url = reverse('web:branch_approve_action', kwargs={'action_id': action.id})
        response = self.client.post(url, {'notes': 'ok'})
        self.assertEqual(response.status_code, 302)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.PENDING_BRANCH)
