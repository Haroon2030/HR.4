"""اختبارات استيراد موظفين بكفالة من Excel (أعمدة النظام الجديدة)."""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from apps.core.models import Branch, Company
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department
from apps.employees.models import Employee, SalaryAccountType
from apps.employees.services.sponsored_import import field_for_header
from apps.setup.models import Bank, Nationality, Sponsorship

User = get_user_model()

HEADERS = [
    'رقم الموظف', 'الاسم', 'رقم الايبان', 'البنك', 'طبيعة الحساب', 'رقم الهوية',
    'الفرع', 'الشركة', 'الراتب الأساسي', 'بدل السكن', 'بدل النقل',
    'بدل إضافي ثاب / حوافز', 'بدل إضافي', 'الجنس', 'الجنسية', 'القسم',
    'مركز التكلفة', 'تاريخ المباشرة',
]


def _xlsx(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@override_settings(ALLOWED_HOSTS=['testserver'])
class SponsoredEmployeesExcelImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة')
        cls.branch = Branch.objects.create(name='فرع جدة', code='SP1', company=company)
        Department.objects.create(code='D1', name='المستودع', branch=cls.branch)
        CostCenter.objects.create(code='C1', name='مركز أ', branch=cls.branch)
        Nationality.objects.create(name='يمني', code='YE')
        cls.bank = Bank.objects.create(code='B1', name='الراجحي')
        cls.sponsorship = Sponsorship.objects.create(
            code='SP-A', company_name='شركة الرشيد', is_active=True,
        )
        cls.admin = User.objects.create_user(
            username='sp_import_admin', password='pass12345',
            is_superuser=True, is_staff=True,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)
        self.url = reverse('web:import_sponsored_employees_excel')

    def _post(self, rows, headers=None):
        uploaded = SimpleUploadedFile(
            'sp.xlsx', _xlsx(headers or HEADERS, rows),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        return self.client.post(self.url, {'excel_file': uploaded}, follow=True)

    def _row(self, **over):
        base = {
            'رقم الموظف': '9001', 'الاسم': 'موظف بكفالة', 'رقم الايبان': 'sa03 8000 0000 6080 1016 7519',
            'البنك': 'الراجحي', 'طبيعة الحساب': 'SALARY CARD', 'رقم الهوية': '2200110011',
            'الفرع': 'فرع جدة', 'الشركة': 'شركة الرشيد', 'الراتب الأساسي': 3000,
            'بدل السكن': 750, 'بدل النقل': 250, 'بدل إضافي ثاب / حوافز': 400,
            'بدل إضافي': 100, 'الجنس': 'ذكر', 'الجنسية': 'يمني', 'القسم': 'المستودع',
            'مركز التكلفة': 'مركز أ', 'تاريخ المباشرة': date(2025, 1, 1),
        }
        base.update(over)
        return [base[h] for h in HEADERS]

    def test_header_aliases(self):
        self.assertEqual(field_for_header('بدل إضافي ثاب / حوافز'), 'incentive_allowance')
        self.assertEqual(field_for_header('بدل إضافي ثابت / حوافز'), 'incentive_allowance')
        self.assertEqual(field_for_header('بدل إضافي'), 'other_allowance')
        self.assertEqual(field_for_header('رقم الايبان'), 'iban')
        self.assertEqual(field_for_header('رقم الآيبان'), 'iban')
        self.assertEqual(field_for_header('الشركة'), 'sponsorship')

    def test_list_page_has_sponsored_import_button(self):
        response = self.client.get(reverse('web:list_employees'))
        self.assertContains(response, 'استيراد بكفالة')
        self.assertContains(response, self.url)

    def test_import_creates_sponsored_employee_with_all_fields(self):
        self._post([self._row()])
        emp = Employee.objects.get(employee_number='9001')
        self.assertEqual(emp.sponsorship_id, self.sponsorship.pk)
        self.assertEqual(emp.bank_id, self.bank.pk)
        self.assertEqual(emp.iban, 'SA0380000000608010167519')
        self.assertEqual(emp.account_type, SalaryAccountType.SALARY_CARD)
        self.assertEqual(emp.gender, 'male')
        self.assertEqual(emp.basic_salary, Decimal('3000.00'))
        self.assertEqual(emp.housing_allowance, Decimal('750.00'))
        self.assertEqual(emp.transport_allowance, Decimal('250.00'))
        self.assertEqual(emp.incentive_allowance, Decimal('400.00'))
        self.assertEqual(emp.other_allowance, Decimal('100.00'))
        self.assertEqual(emp.total_salary, Decimal('4500.00'))
        self.assertEqual(emp.branch_id, self.branch.pk)
        self.assertEqual(emp.hire_date, date(2025, 1, 1))

    def test_import_updates_existing_by_employee_number(self):
        self._post([self._row()])
        self._post([self._row(**{'الراتب الأساسي': 3500})])
        self.assertEqual(Employee.objects.filter(employee_number='9001').count(), 1)
        self.assertEqual(
            Employee.objects.get(employee_number='9001').basic_salary, Decimal('3500.00'),
        )

    def test_unknown_company_is_row_error(self):
        self._post([self._row(**{'الشركة': 'شركة غير موجودة'})])
        self.assertFalse(Employee.objects.filter(employee_number='9001').exists())
