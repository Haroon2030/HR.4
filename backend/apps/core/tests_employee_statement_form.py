"""نموذج «إفادة»: يظهر في فهرس النماذج ويُطبع ببيانات الموظف."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Branch, Company
from apps.employees.models import Employee

User = get_user_model()


class EmployeeStatementFormTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='Co-ES', tax_number='1', commercial_record='1')
        branch = Branch.objects.create(name='سكاي مول', code='ES-1', company=company)
        self.employee = Employee.objects.create(
            name='هارون اختبار', branch=branch, employee_number='4321', id_number='1234567890',
        )
        self.admin = User.objects.create_superuser(username='es_admin', password='Pass-User-99!')
        self.client.force_login(self.admin)

    def test_form_is_listed_in_forms_index(self):
        resp = self.client.get(reverse('web:hr_forms_index'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'نموذج إفادة')

    def test_print_shows_employee_data_and_signature_boxes(self):
        resp = self.client.get(reverse('web:hr_form_print', args=['employee_statement', self.employee.id]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        for text in ('هارون اختبار', '4321', '1234567890', 'سكاي مول', 'إفادة الموظف', 'المدير المباشر', 'الموارد البشرية'):
            self.assertIn(text, html)
