"""ربط المستخدم بالإدارات — تقييد رؤية الموظفين وفرض الإدارة عند الإضافة."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import AppModule, Branch, Company, Permission, Role
from apps.core.services.access_control import (
    filter_employees_for_user,
    get_scoped_administration_ids,
    user_may_access_employee,
)
from apps.employees.models import Employee, EmploymentRequest
from apps.setup.models import Administration

User = get_user_model()


def _permission(module_code: str, code: str, operation: str) -> Permission:
    module, _ = AppModule.objects.get_or_create(
        code=module_code,
        defaults={'name': module_code, 'icon': 'circle', 'order': 50},
    )
    perm, _ = Permission.objects.get_or_create(
        code=code,
        defaults={'module': module, 'operation': operation, 'name': code},
    )
    return perm


class AdministrationScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch_1 = Branch.objects.create(name='B1', code='B1', company=company)
        cls.branch_2 = Branch.objects.create(name='B2', code='B2', company=company)

        cls.admin_a = Administration.objects.create(code='A', name='إدارة أ')
        cls.admin_b = Administration.objects.create(code='B', name='إدارة ب')

        cls.emp_a_branch1 = Employee.objects.create(
            name='موظف أ1', branch=cls.branch_1, administration=cls.admin_a,
        )
        cls.emp_a_branch2 = Employee.objects.create(
            name='موظف أ2', branch=cls.branch_2, administration=cls.admin_a,
        )
        cls.emp_b_branch1 = Employee.objects.create(
            name='موظف ب1', branch=cls.branch_1, administration=cls.admin_b,
        )
        cls.emp_no_admin = Employee.objects.create(name='بدون إدارة', branch=cls.branch_1)

        cls.data_entry_role = Role.objects.create(name='Data entry', role_type=Role.RoleType.SPECIALIST)
        cls.data_entry_role.permissions.add(
            _permission('employees', 'employees.view', Permission.Operation.VIEW),
            _permission('employees', 'employees.add', Permission.Operation.ADD),
            _permission('users', 'users.view', Permission.Operation.VIEW),
            _permission('users', 'users.add', Permission.Operation.ADD),
        )
        cls.admin_role = Role.objects.create(
            name='Admin', role_type=Role.RoleType.ADMIN, is_system_role=True,
        )

        cls.linked_user = cls._make_user('linked', cls.data_entry_role, branch=cls.branch_1)
        cls.linked_user.profile.assigned_administrations.add(cls.admin_a)

        cls.branch_user = cls._make_user('branch_only', cls.data_entry_role, branch=cls.branch_1)

        cls.admin_user = cls._make_user('sysadmin', cls.admin_role)
        cls.admin_user.profile.assigned_administrations.add(cls.admin_a)

        cls.hr_officer_role = Role.objects.create(name='HR officer', role_type=Role.RoleType.HR_OFFICER)
        cls.hr_officer_role.permissions.add(
            _permission('employees', 'employees.view', Permission.Operation.VIEW),
        )
        cls.hr_officer = cls._make_user('hr_officer', cls.hr_officer_role, branch=cls.branch_1)
        cls.hr_officer.profile.assigned_administrations.add(cls.admin_a)

    @staticmethod
    def _make_user(username, role, branch=None):
        user = User.objects.create_user(username=username, password='Pass-User-99!')
        profile = user.profile
        profile.role = role
        profile.branch = branch
        profile.save()
        return user

    def _fresh(self, user):
        return User.objects.get(pk=user.pk)

    def _names(self, user):
        qs = filter_employees_for_user(self._fresh(user), Employee.objects.all())
        return set(qs.values_list('name', flat=True))

    # ── service layer ────────────────────────────────────────────────

    def test_linked_user_sees_only_administration_employees_across_branches(self):
        self.assertEqual(self._names(self.linked_user), {'موظف أ1', 'موظف أ2'})

    def test_unlinked_user_keeps_branch_scope(self):
        self.assertEqual(
            self._names(self.branch_user),
            {'موظف أ1', 'موظف ب1', 'بدون إدارة'},
        )

    def test_privileged_user_is_not_restricted_by_link(self):
        self.assertIsNone(get_scoped_administration_ids(self._fresh(self.admin_user)))
        self.assertEqual(self._names(self.admin_user), set(Employee.objects.values_list('name', flat=True)))

    def test_hr_officer_sees_all_employees_even_when_linked(self):
        self.assertIsNone(get_scoped_administration_ids(self._fresh(self.hr_officer)))
        self.assertEqual(
            self._names(self.hr_officer),
            set(Employee.objects.values_list('name', flat=True)),
        )

    def test_managed_administration_is_added_to_linked_scope(self):
        self.admin_b.manager = self.linked_user
        self.admin_b.save(update_fields=['manager'])
        self.assertEqual(self._names(self.linked_user), {'موظف أ1', 'موظف أ2', 'موظف ب1'})

    def test_object_access_follows_administration_link(self):
        user = self._fresh(self.linked_user)
        self.assertTrue(user_may_access_employee(user, self.emp_a_branch2))
        self.assertFalse(user_may_access_employee(user, self.emp_b_branch1))
        self.assertFalse(user_may_access_employee(user, self.emp_no_admin))

    # ── web views ────────────────────────────────────────────────────

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_employee_list_shows_only_linked_administration(self):
        response = self._client_for(self.linked_user).get(reverse('web:list_employees'))
        self.assertEqual(response.status_code, 200)
        names = {e.name for e in response.context['employees']}
        self.assertEqual(names, {'موظف أ1', 'موظف أ2'})

    def test_hr_officer_employee_list_shows_all_employees(self):
        client = self._client_for(self.hr_officer)
        response = client.get(reverse('web:list_employees'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_count'], Employee.objects.count())

        profile = client.get(reverse('web:view_employee', kwargs={'employee_id': self.emp_b_branch1.pk}))
        self.assertEqual(profile.status_code, 200)

    def test_employee_profile_outside_administration_is_blocked(self):
        client = self._client_for(self.linked_user)
        blocked = client.get(reverse('web:view_employee', kwargs={'employee_id': self.emp_b_branch1.pk}))
        self.assertRedirects(blocked, reverse('web:list_employees'), fetch_redirect_response=False)

    def test_add_employee_preselects_single_linked_administration(self):
        response = self._client_for(self.linked_user).get(reverse('web:add_employee'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['default_administration_id'], self.admin_a.pk)
        self.assertEqual([a.pk for a in response.context['administrations']], [self.admin_a.pk])

    def test_add_employee_rejects_other_or_missing_administration(self):
        client = self._client_for(self.linked_user)
        url = reverse('web:add_employee')
        client.post(url, {'name': 'مرفوض ب', 'administration': self.admin_b.pk})
        client.post(url, {'name': 'مرفوض فارغ', 'administration': ''})
        self.assertFalse(
            EmploymentRequest.objects.filter(name__in=['مرفوض ب', 'مرفوض فارغ']).exists()
        )

        client.post(url, {'name': 'مقبول أ', 'administration': self.admin_a.pk})
        created = EmploymentRequest.objects.get(name='مقبول أ')
        self.assertEqual(created.administration_id, self.admin_a.pk)
        self.assertEqual(created.requested_by_id, self.linked_user.pk)

    def test_non_privileged_actor_cannot_link_administrations(self):
        client = self._client_for(self.linked_user)
        client.post(reverse('web:add_user'), {
            'username': 'new_by_specialist',
            'password': '123456',
            'role': self.data_entry_role.pk,
            'branch': self.branch_1.pk,
            'assigned_administrations': [self.admin_b.pk],
        })
        created = User.objects.get(username='new_by_specialist')
        self.assertFalse(created.profile.assigned_administrations.exists())

    def test_admin_can_link_and_unlink_administrations(self):
        target = self._make_user('target', self.data_entry_role, branch=self.branch_1)
        client = self._client_for(self.admin_user)
        url = reverse('web:edit_user', kwargs={'user_id': target.pk})
        base = {'username': 'target', 'role': self.data_entry_role.pk, 'branch': self.branch_1.pk}

        client.post(url, {**base, 'assigned_administrations': [self.admin_a.pk, self.admin_b.pk]})
        self.assertEqual(
            set(target.profile.assigned_administrations.values_list('pk', flat=True)),
            {self.admin_a.pk, self.admin_b.pk},
        )

        client.post(url, base)
        self.assertFalse(target.profile.assigned_administrations.exists())
