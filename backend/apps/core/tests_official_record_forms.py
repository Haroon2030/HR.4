"""نماذج رسمية لسجل واحد: السلفة والغياب (طباعة رسمية)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Branch, Company
from apps.employees.models import (
    Employee, EmployeeAbsence, EmployeeCustody, EmployeeLeave, EmployeeLoan, EmployeeStatement,
)

User = get_user_model()


class OfficialRecordFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='B1', code='B1', company=company)
        cls.admin = User.objects.create_superuser(username='root', password='Pass-User-99!', email='r@e.co')
        cls.employee = Employee.objects.create(name='موظف تجريبي', branch=cls.branch, id_number='1234567890')
        cls.loan = EmployeeLoan.objects.create(
            employee=cls.employee, amount=Decimal('5000'), monthly_deduction=Decimal('500'),
            installments=10, reason='ظرف طارئ', issued_at=date(2026, 6, 24),
            first_deduction_date=date(2026, 7, 1),
        )
        cls.absence = EmployeeAbsence.objects.create(
            employee=cls.employee, absence_date=date(2026, 9, 1), days=2,
            reason='ظرف عائلي', notes='تم التبليغ هاتفياً',
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_loan_form_is_prefilled_from_the_loan(self):
        response = self.client.get(reverse('web:print_loan_form', args=[self.employee.id, self.loan.id]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('5000.00', html)
        self.assertIn('خمسة آلاف ريال سعودي فقط لا غير', html)
        self.assertIn('ظرف طارئ', html)
        self.assertIn('2026/07/01', html)
        self.assertIn('موظف تجريبي', html)

    def test_absence_form_is_prefilled_from_the_absence(self):
        response = self.client.get(reverse('web:print_absence_form', args=[self.employee.id, self.absence.id]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('2026/09/01', html)
        self.assertIn('يومان', html)
        self.assertIn('ظرف عائلي', html)
        self.assertIn('تم التبليغ هاتفياً', html)

    def test_record_must_belong_to_the_employee(self):
        other = Employee.objects.create(name='آخر', branch=self.branch)
        response = self.client.get(reverse('web:print_loan_form', args=[other.id, self.loan.id]))
        self.assertEqual(response.status_code, 404)

    def test_forms_appear_in_official_forms_index(self):
        response = self.client.get(reverse('web:hr_forms_index'))
        keys = [f['key'] for f in response.context['forms']]
        self.assertIn('absence_notice', keys)
        self.assertIn('loan_request', keys)

    def test_employee_page_links_to_official_print(self):
        loan_url = reverse('web:print_loan_form', args=[self.employee.id, self.loan.id])
        response = self.client.get(reverse('web:view_employee', args=[self.employee.id]) + '?tab=loans')
        self.assertContains(response, loan_url)


class OfficialRecordFormsMoreTests(TestCase):
    """إجازة وعهدة وإفادات/إنذارات."""

    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='B1', code='B1', company=company)
        cls.admin = User.objects.create_superuser(username='root2', password='Pass-User-99!', email='r2@e.co')
        cls.employee = Employee.objects.create(name='موظف تجريبي', branch=cls.branch)
        cls.leave = EmployeeLeave.objects.create(
            employee=cls.employee, leave_type='sick', date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 3), days=Decimal('3'), notes='مراجعة طبيب',
        )
        cls.custody = EmployeeCustody.objects.create(
            employee=cls.employee, item_name='لابتوب', item_details='Dell 5420', quantity=1,
            estimated_value=Decimal('3500'), received_at=date(2026, 5, 1),
            status='returned', returned_at=date(2026, 9, 10), return_notes='انتهاء المشروع',
        )
        cls.warning = EmployeeStatement.objects.create(
            employee=cls.employee, statement_type='warning', title='تأخر متكرر',
            statement_date=date(2026, 9, 5), content='تأخر ثلاث مرات', serial_number='WRN-2026-0001',
        )
        cls.statement = EmployeeStatement.objects.create(
            employee=cls.employee, statement_type='statement', title='إفادة راتب',
            statement_date=date(2026, 9, 6), content='نص الإفادة', serial_number='STM-2026-0001',
        )
        cls.terminate = EmployeeStatement.objects.create(
            employee=cls.employee, statement_type='terminate', title='تصفية',
            statement_date=date(2026, 9, 7), serial_number='TRM-2026-0001',
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_leave_form_is_prefilled(self):
        response = self.client.get(reverse('web:print_leave_form', args=[self.employee.id, self.leave.id]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('2026/09/01', html)
        self.assertIn('2026/09/03', html)
        self.assertIn('2026/09/04', html)  # تاريخ المباشرة = اليوم التالي لنهاية الإجازة
        self.assertIn('مراجعة طبيب', html)
        self.assertRegex(html, r'<span class="box" data-checked></span> إجازة مرضية')

    def test_custody_receipt_and_clearance(self):
        receipt = self.client.get(reverse('web:print_custody_form', args=[self.employee.id, self.custody.id]))
        self.assertEqual(receipt.status_code, 200)
        self.assertIn('لابتوب', receipt.content.decode())
        self.assertIn('2026/05/01', receipt.content.decode())
        clearance = self.client.get(
            reverse('web:print_custody_form', args=[self.employee.id, self.custody.id]) + '?kind=clearance'
        )
        self.assertEqual(clearance.status_code, 200)
        self.assertIn('2026/09/10', clearance.content.decode())
        self.assertIn('انتهاء المشروع', clearance.content.decode())

    def test_warning_and_generic_statement_forms(self):
        warning = self.client.get(reverse('web:print_statement_form', args=[self.employee.id, self.warning.id]))
        self.assertEqual(warning.status_code, 200)
        self.assertIn('تأخر متكرر', warning.content.decode())
        self.assertIn('WRN-2026-0001', warning.content.decode())
        generic = self.client.get(reverse('web:print_statement_form', args=[self.employee.id, self.statement.id]))
        self.assertEqual(generic.status_code, 200)
        self.assertIn('نص الإفادة', generic.content.decode())
        self.assertIn('STM-2026-0001', generic.content.decode())

    def test_termination_statement_redirects_to_final_settlement(self):
        response = self.client.get(reverse('web:print_statement_form', args=[self.employee.id, self.terminate.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('final_settlement', response['Location'])
        self.assertIn(f'stmt_id={self.terminate.id}', response['Location'])

    def test_tabs_render_with_print_links(self):
        view = reverse('web:view_employee', args=[self.employee.id])
        cases = {
            'custodies': reverse('web:print_custody_form', args=[self.employee.id, self.custody.id]),
            'leaves': reverse('web:print_leave_form', args=[self.employee.id, self.leave.id]),
            'warnings': reverse('web:print_statement_form', args=[self.employee.id, self.warning.id]),
        }
        for tab, url in cases.items():
            response = self.client.get(f'{view}?tab={tab}')
            self.assertEqual(response.status_code, 200, tab)
            self.assertContains(response, url, msg_prefix=tab)
            self.assertContains(response, 'data-hr-dyn', msg_prefix=tab)
        clearance = cases['custodies'] + '?kind=clearance'
        self.assertContains(self.client.get(f'{view}?tab=custodies'), clearance)
