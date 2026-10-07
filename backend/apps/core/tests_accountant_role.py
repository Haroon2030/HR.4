"""دور المحاسب: اطّلاع شامل + تعميد ما يديره فقط، بلا إضافة/تعديل/حذف."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.decorators import get_user_permissions
from apps.core.models import Branch, Company, PendingAction, Permission, Role
from apps.core.role_policies import is_read_operation, sync_accountant_role
from apps.core.services.access_control import get_accessible_branch_ids, user_may_access_employee
from apps.core.services.approval_routing import user_can_first_approve
from apps.employees.models import Employee
from apps.setup.models import Administration

User = get_user_model()


class AccountantRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch1 = Branch.objects.create(name='B1', code='B1', company=company)
        cls.branch2 = Branch.objects.create(name='B2', code='B2', company=company)

        cls.role = Role.objects.create(name='Accountant', role_type=Role.RoleType.BRANCH_ACCOUNTANT)
        # بداية خاطئة: صلاحيات كتابة ممنوحة سابقاً يجب أن تُزال
        cls.role.permissions.set(Permission.objects.filter(
            code__in=['employees.view', 'cash_shortages.add', 'employees.edit'],
        ))
        sync_accountant_role(Role, Permission)

        cls.accountant = User.objects.create_user(username='acct', password='Pass-User-99!')
        cls.accountant.profile.role = cls.role
        cls.accountant.profile.branch = cls.branch1
        cls.accountant.profile.save()

        cls.finance = Administration.objects.create(code='FIN', name='الإدارة المالية', manager=cls.accountant)
        cls.other_manager = User.objects.create_user(username='opsmgr', password='Pass-User-99!')
        cls.operations = Administration.objects.create(code='OPS', name='العمليات', manager=cls.other_manager)

        cls.finance_emp = Employee.objects.create(name='موظف مالي', branch=cls.branch1, administration=cls.finance)
        cls.ops_emp = Employee.objects.create(name='موظف عمليات', branch=cls.branch2, administration=cls.operations)

    def _fresh(self):
        return User.objects.get(pk=self.accountant.pk)

    def _action(self, employee):
        return PendingAction.objects.create(
            action_type='loan_request', employee=employee,
            branch=employee.branch, administration=employee.administration,
            payload={'amount': '100', 'monthly_deduction': '50', 'issued_at': date.today().isoformat()},
            requested_by=self.other_manager,
        )

    def test_role_has_all_view_permissions_and_no_write_permissions(self):
        codes = get_user_permissions(self._fresh())
        for expected in ('employees.view', 'payroll.view', 'operations.view', 'cash_shortages.view',
                         'operations.approve_admin', 'operations.return'):
            self.assertIn(expected, codes, expected)
        for forbidden in ('employees.add', 'employees.edit', 'employees.delete', 'cash_shortages.add',
                          'employees.edit_loan', 'payroll.process', 'operations.approve_gm',
                          'users.add', 'users.edit', 'employee_tab_termination.execute'):
            self.assertNotIn(forbidden, codes, forbidden)
        write_like = [c for c in codes if not is_read_operation(c.split('.', 1)[1])
                      and c not in ('operations.approve_admin', 'operations.approve_branch', 'operations.return')]
        self.assertEqual(write_like, [])

    def test_sees_every_employee_in_every_branch(self):
        accountant = self._fresh()
        self.assertIsNone(get_accessible_branch_ids(accountant))
        self.assertTrue(user_may_access_employee(accountant, self.finance_emp))
        self.assertTrue(user_may_access_employee(accountant, self.ops_emp))

    def test_approves_only_the_administration_he_manages(self):
        accountant = self._fresh()
        self.assertTrue(user_can_first_approve(accountant, self._action(self.finance_emp)))
        self.assertFalse(user_can_first_approve(accountant, self._action(self.ops_emp)))

    def test_cannot_edit_add_or_delete_anything(self):
        self.client.force_login(self.accountant)
        for url, method in (
            (reverse('web:edit_employee', args=[self.finance_emp.id]), 'post'),
            (reverse('web:add_employee_loan', args=[self.finance_emp.id]), 'post'),
            (reverse('web:add_employee_leave', args=[self.finance_emp.id]), 'post'),
            (reverse('web:delete_employee', args=[self.finance_emp.id]), 'post'),
            (reverse('web:add_employee'), 'get'),
        ):
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertEqual(response['Location'], reverse('web:dashboard'), url)
        self.assertTrue(Employee.objects.filter(pk=self.finance_emp.pk).exists())

    def test_can_view_employee_profile_without_edit_buttons(self):
        self.client.force_login(self.accountant)
        response = self.client.get(reverse('web:view_employee', args=[self.ops_emp.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('web:edit_employee', args=[self.ops_emp.id]))
        self.assertNotContains(response, 'إضافة سريعة')

    def test_new_view_permissions_are_added_automatically(self):
        from apps.core.models import AppModule

        module = AppModule.objects.create(code='newmod', name='جديدة', icon='circle', order=999)
        view_perm = Permission.objects.create(code='newmod.view', module=module, operation='view', name='v')
        add_perm = Permission.objects.create(code='newmod.add', module=module, operation='add', name='a')
        sync_accountant_role(Role, Permission, additive_only=True)
        codes = set(self.role.permissions.values_list('code', flat=True))
        self.assertIn(view_perm.code, codes)
        self.assertNotIn(add_perm.code, codes)
