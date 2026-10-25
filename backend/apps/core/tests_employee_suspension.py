"""اختبارات زر توقيف الموظف — مدير الموارد البشرية والسوبر أدمن فقط."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Branch, Company, Permission, Role, UserProfile
from apps.employees.models import Employee
from apps.employees.services.suspension import user_can_suspend_employees

User = get_user_model()


class EmployeeSuspensionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة')
        cls.branch = Branch.objects.create(name='فرع', code='BR-S', company=company)
        view_edit = list(Permission.objects.filter(code__in=['employees.view', 'employees.edit']))
        cls.hr_manager_role = Role.objects.create(name='HR Manager S', role_type=Role.RoleType.HR_MANAGER)
        cls.hr_manager_role.permissions.add(*view_edit)
        cls.officer_role = Role.objects.create(name='HR Officer S', role_type=Role.RoleType.HR_OFFICER)
        cls.officer_role.permissions.add(*view_edit)

    def setUp(self):
        self.employee = Employee.objects.create(
            name='موظف', branch=self.branch, status=Employee.Status.ACTIVE,
            basic_salary=Decimal('3000'),
        )
        self.url = reverse('web:toggle_employee_suspension', args=[self.employee.id])

    def _user(self, username, role=None, **kwargs):
        user = User.objects.create_user(username=username, password='x', **kwargs)
        if role is not None:
            profile = UserProfile.objects.get(user=user)
            profile.role = role
            profile.save(update_fields=['role', 'updated_at'])
        return User.objects.select_related('profile__role').get(pk=user.pk)

    def _status(self):
        self.employee.refresh_from_db()
        return self.employee.status

    def test_permission_rule(self):
        self.assertTrue(user_can_suspend_employees(self._user('su', is_superuser=True, is_staff=True)))
        self.assertTrue(user_can_suspend_employees(self._user('mgr', self.hr_manager_role)))
        self.assertFalse(user_can_suspend_employees(self._user('off', self.officer_role)))

    def test_superuser_suspends_and_unsuspends(self):
        self.client.force_login(self._user('su', is_superuser=True, is_staff=True))
        self.client.post(self.url)
        self.assertEqual(self._status(), Employee.Status.SUSPENDED)
        self.client.post(self.url)
        self.assertEqual(self._status(), Employee.Status.ACTIVE)

    def test_hr_manager_can_suspend(self):
        self.client.force_login(self._user('mgr', self.hr_manager_role))
        self.client.post(self.url)
        self.assertEqual(self._status(), Employee.Status.SUSPENDED)

    def test_other_role_with_edit_permission_cannot_suspend(self):
        from django.contrib.messages import get_messages
        self.client.force_login(self._user('off', self.officer_role))
        r = self.client.post(self.url)
        self.assertEqual(self._status(), Employee.Status.ACTIVE)
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertTrue(any('مدير الموارد' in m for m in msgs), msgs)

    def test_get_does_not_change_status(self):
        self.client.force_login(self._user('su', is_superuser=True, is_staff=True))
        self.client.get(self.url)
        self.assertEqual(self._status(), Employee.Status.ACTIVE)

    def test_terminated_employee_cannot_be_suspended(self):
        self.employee.status = Employee.Status.TERMINATED
        self.employee.save(update_fields=['status'])
        self.client.force_login(self._user('su', is_superuser=True, is_staff=True))
        self.client.post(self.url)
        self.assertEqual(self._status(), Employee.Status.TERMINATED)
