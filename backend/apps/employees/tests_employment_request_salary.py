"""حقل الراتب الأساسي في نموذج رفع طلب التوظيف (شاشة إضافة موظف)."""
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AppModule, Branch, Company, Permission, Role
from apps.employees.models import EmploymentRequest

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class EmploymentRequestSalaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='B1', code='B1', company=company)

        module, _ = AppModule.objects.get_or_create(
            code='employees', defaults={'name': 'employees', 'icon': 'circle', 'order': 50},
        )
        add_perm, _ = Permission.objects.get_or_create(
            code='employees.add',
            defaults={'module': module, 'operation': Permission.Operation.ADD, 'name': 'add'},
        )
        role = Role.objects.create(name='Data entry', role_type=Role.RoleType.SPECIALIST)
        role.permissions.add(add_perm)

        cls.user = User.objects.create_user(username='entry', password='Pass-User-99!')
        profile = cls.user.profile
        profile.role = role
        profile.branch = cls.branch
        profile.save()

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse('web:add_employee')

    @staticmethod
    def _document():
        return SimpleUploadedFile('commencement.pdf', b'%PDF-1.4 test', content_type='application/pdf')

    def _submit(self, name, with_document=True, **extra):
        data = {'name': name, 'branch': self.branch.pk, 'basic_salary': '3000', **extra}
        if with_document:
            data['commencement_document'] = self._document()
        return self.client.post(self.url, data)

    def test_add_employee_page_renders_basic_salary_field(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="basic_salary"')

    def test_submitted_salary_is_saved_on_request(self):
        self._submit('براتب', basic_salary='4500.50')
        request_obj = EmploymentRequest.objects.get(name='براتب')
        self.assertEqual(request_obj.basic_salary, Decimal('4500.50'))
        self.assertEqual(request_obj.requested_by_id, self.user.pk)

    def test_missing_or_zero_salary_is_rejected(self):
        self._submit('بدون راتب', basic_salary='')
        self._submit('راتب صفر', basic_salary='0')
        self.assertFalse(
            EmploymentRequest.objects.filter(name__in=['بدون راتب', 'راتب صفر']).exists()
        )

    def test_missing_commencement_document_is_rejected(self):
        self._submit('بدون مستند', with_document=False)
        self.assertFalse(EmploymentRequest.objects.filter(name='بدون مستند').exists())

    def test_negative_salary_is_rejected(self):
        self._submit('راتب سالب', basic_salary='-10')
        self.assertFalse(EmploymentRequest.objects.filter(name='راتب سالب').exists())
