"""آيبان نموذج التصفية للمُصفّى على كفالة، وصلاحيات الراتب لأخصائي الموارد."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Branch, Company, Permission, Role
from apps.core.salary_access import user_can_edit_salary, user_can_view_salary
from apps.employees.models import Employee
from apps.setup.models import Sponsorship

User = get_user_model()
IBAN = 'SA0380000000608010167519'


class SettlementIbanTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        self.branch = Branch.objects.create(name='B1', code='IB1', company=company)
        self.sponsorship = Sponsorship.objects.create(code='SP1', company_name='كفيل')
        self.admin = User.objects.create_superuser(username='ibroot', password='Pass-User-99!', email='i@e.co')
        self.client.force_login(self.admin)

    def _page(self, **kw):
        emp = Employee.objects.create(
            name='موظف', branch=self.branch, iban=IBAN, hire_date=date(2026, 1, 12),
            end_date=date(2026, 10, 23), basic_salary=2400, **kw,
        )
        return self.client.get(reverse('web:hr_form_print', args=['final_settlement', emp.id])).content.decode()

    def test_iban_shown_when_on_sponsorship(self):
        self.assertIn(IBAN, self._page(sponsorship=self.sponsorship))

    def test_iban_hidden_when_not_on_sponsorship(self):
        self.assertNotIn(IBAN, self._page())


class HrOfficerSalaryPermissionTests(TestCase):
    def test_migration_grants_view_and_edit_salary(self):
        import importlib
        from django.apps import apps as django_apps
        from apps.core.models import AppModule
        AppModule.objects.get_or_create(code='employees', defaults={'name': 'employees', 'icon': 'users', 'order': 1})
        role = Role.objects.create(name='أخصائي موارد', role_type=Role.RoleType.HR_OFFICER)
        user = User.objects.create_user('hro', password='x')
        user.profile.role = role
        user.profile.save(update_fields=['role'])
        self.assertFalse(user_can_edit_salary(user))
        importlib.import_module('apps.core.migrations.0061_hr_officer_salary_permissions').forward(django_apps, None)
        user = User.objects.get(pk=user.pk)
        self.assertTrue(user_can_view_salary(user))
        self.assertTrue(user_can_edit_salary(user))
