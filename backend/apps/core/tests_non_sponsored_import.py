"""اختبارات استيراد موظفين بدون كفالة من Excel."""
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
from apps.employees.models import Employee
from apps.setup.models import Nationality, Profession, Sponsorship

User = get_user_model()


def _xlsx_bytes(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@override_settings(ALLOWED_HOSTS=['testserver'])
class NonSponsoredEmployeesExcelImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة استيراد')
        cls.branch = Branch.objects.create(name='فرع جدة', code='IM1', company=company)
        cls.department = Department.objects.create(code='D1', name='الموارد', branch=cls.branch)
        cls.cost_center = CostCenter.objects.create(code='C1', name='مركز تشغيل', branch=cls.branch)
        cls.nationality = Nationality.objects.create(name='سعودي', code='SA')
        cls.profession = Profession.objects.create(name='محاسب', code='ACC')
        cls.sponsorship = Sponsorship.objects.create(
            code='SP-IM',
            company_name='كفالة استيراد',
            is_active=True,
        )
        cls.admin = User.objects.create_user(
            username='import_admin',
            password='pass12345',
            is_superuser=True,
            is_staff=True,
        )
        cls.existing = Employee.objects.create(
            name='قديم بدون كفالة',
            employee_number='8001',
            id_number='100200300',
            phone='0501111111',
            branch=cls.branch,
            sponsorship=None,
            basic_salary=Decimal('2000.00'),
            status=Employee.Status.ACTIVE,
        )
        cls.sponsored = Employee.objects.create(
            name='على كفالة',
            employee_number='8002',
            id_number='200300400',
            phone='0502222222',
            branch=cls.branch,
            sponsorship=cls.sponsorship,
            status=Employee.Status.ACTIVE,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)
        self.url = reverse('web:import_non_sponsored_employees_excel')
        self.headers = [
            'الاسم',
            'رقم الهوية',
            'رقم الجوال',
            'الرقم الوظيفي',
            'تاريخ المباشرة',
            'الجنسية',
            'المهنة',
            'الراتب الأساسي',
            'الفرع',
            'القسم',
            'مركز التكلفة',
        ]

    def _post_xlsx(self, rows, headers=None):
        content = _xlsx_bytes(headers or self.headers, rows)
        uploaded = SimpleUploadedFile(
            'import.xlsx',
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        return self.client.post(self.url, {'excel_file': uploaded}, follow=True)

    def test_list_page_has_import_button(self):
        response = self.client.get(reverse('web:list_employees'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'استيراد بدون كفالة')
        self.assertContains(response, reverse('web:import_non_sponsored_employees_excel'))

    def test_import_creates_employee(self):
        response = self._post_xlsx([[
            'موظف جديد',
            '555666777',
            '0555555555',
            '8100',
            date(2025, 3, 1),
            'سعودي',
            'محاسب',
            4500.25,
            'فرع جدة',
            'الموارد',
            'مركز تشغيل',
        ]])
        self.assertEqual(response.status_code, 200)
        emp = Employee.objects.get(employee_number='8100')
        self.assertEqual(emp.name, 'موظف جديد')
        self.assertIsNone(emp.sponsorship_id)
        self.assertEqual(emp.id_number, '555666777')
        self.assertEqual(emp.phone, '0555555555')
        self.assertEqual(emp.hire_date, date(2025, 3, 1))
        self.assertEqual(emp.branch_id, self.branch.id)
        self.assertEqual(emp.department_id, self.department.id)
        self.assertIsNone(emp.administration_id)
        self.assertEqual(emp.cost_center_id, self.cost_center.id)
        self.assertEqual(emp.nationality_id, self.nationality.id)
        self.assertEqual(emp.profession_id, self.profession.id)
        self.assertEqual(emp.basic_salary, Decimal('4500.25'))

    def test_import_updates_existing_non_sponsored(self):
        response = self._post_xlsx([[
            'قديم محدّث',
            '100200300',
            '0509999999',
            '8001',
            date(2024, 6, 10),
            'سعودي',
            'محاسب',
            3100,
            'فرع جدة',
            'الموارد',
            'مركز تشغيل',
        ]])
        self.assertEqual(response.status_code, 200)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, 'قديم محدّث')
        self.assertEqual(self.existing.phone, '0509999999')
        self.assertEqual(self.existing.basic_salary, Decimal('3100.00'))
        self.assertIsNone(self.existing.sponsorship_id)

    def test_import_skips_sponsored_employee(self):
        before = Employee.objects.filter(sponsorship__isnull=False).count()
        response = self._post_xlsx([[
            'محاولة تعديل كفالة',
            '200300400',
            '0500000000',
            '8002',
            date(2024, 1, 1),
            'سعودي',
            'محاسب',
            1000,
            'فرع جدة',
            'الموارد',
            'مركز تشغيل',
        ]])
        self.assertEqual(response.status_code, 200)
        self.sponsored.refresh_from_db()
        self.assertEqual(self.sponsored.name, 'على كفالة')
        self.assertEqual(Employee.objects.filter(sponsorship__isnull=False).count(), before)

    def test_import_rejects_non_xlsx_name(self):
        uploaded = SimpleUploadedFile(
            'import.csv',
            b'name,id\nfoo,1\n',
            content_type='text/csv',
        )
        response = self.client.post(self.url, {'excel_file': uploaded}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Employee.objects.filter(name='foo').exists())

    def test_import_rejects_fake_xlsx_content(self):
        uploaded = SimpleUploadedFile(
            'import.xlsx',
            b'not-a-real-zip-file',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response = self.client.post(self.url, {'excel_file': uploaded}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Excel')
