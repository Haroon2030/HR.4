"""أيام الإجازة السنوية (21–30) لكل موظف — تُحفظ من تبويب الإجازات وتؤثر في التصفية."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Branch, Company
from apps.employees.models import Employee
from apps.employees.services.settlement_eosb import (
    compute_article_80_leave_settlement,
    compute_probation_end_leave_settlement,
)
from apps.setup.models import Sponsorship

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class AnnualLeaveDaysTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة')
        cls.branch = Branch.objects.create(name='فرع', code='BR-AL', company=company)
        cls.sponsorship = Sponsorship.objects.create(code='SP-AL', company_name='K')
        cls.admin = User.objects.create_user(
            username='al_admin', password='x12345678', is_superuser=True, is_staff=True,
        )

    def _employee(self, **kwargs):
        return Employee.objects.create(
            name='موظف', branch=self.branch, sponsorship=self.sponsorship,
            hire_date=date(2017, 1, 1), basic_salary=Decimal('6000'), **kwargs,
        )

    def test_default_is_21_and_unchanged(self):
        emp = self._employee()
        self.assertEqual(emp.annual_leave_days, 21)
        remaining, _, _ = compute_article_80_leave_settlement(employee=emp, as_of=date(2024, 1, 1))
        self.assertEqual(remaining, Decimal('165.00'))

    def test_custom_days_change_settlement(self):
        emp = self._employee(annual_leave_days=25)
        remaining, _, text = compute_article_80_leave_settlement(employee=emp, as_of=date(2024, 1, 1))
        self.assertEqual(remaining, Decimal('185.00'))  # 25 × 5 + 24 شهراً × 30 ÷ 12
        remaining, _, text = compute_probation_end_leave_settlement(employee=emp, as_of=date(2024, 1, 1))
        self.assertEqual(remaining, Decimal('175.00'))  # 84 شهراً × 25 ÷ 12
        self.assertIn('25 يوم/سنة', text)

    def test_save_from_leaves_tab(self):
        emp = self._employee()
        self.client.force_login(self.admin)
        url = reverse('web:save_employee_leave_settings', args=[emp.id])
        self.client.post(url, {'annual_leave_days': '28', 'opening_leave_days': ''})
        emp.refresh_from_db()
        self.assertEqual(emp.annual_leave_days, 28)

    def test_invalid_value_rejected(self):
        emp = self._employee()
        self.client.force_login(self.admin)
        url = reverse('web:save_employee_leave_settings', args=[emp.id])
        for bad in ('20', '31', 'abc'):
            self.client.post(url, {'annual_leave_days': bad, 'opening_leave_days': ''})
            emp.refresh_from_db()
            self.assertEqual(emp.annual_leave_days, 21)

    def test_dropdown_shown_in_leaves_tab(self):
        emp = self._employee(annual_leave_days=26)
        self.client.force_login(self.admin)
        r = self.client.get(reverse('web:view_employee', args=[emp.id]) + '?tab=leaves')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('name="annual_leave_days"', html)
        self.assertIn('<option value="26" selected>', html)
