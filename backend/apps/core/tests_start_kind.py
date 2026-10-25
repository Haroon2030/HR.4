"""خيار «نوع المباشرة» عند رفع موظف جديد: مباشرة جديدة / عودة من إجازة."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Branch, Company
from apps.employees.models import EmploymentRequest

User = get_user_model()

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'


@override_settings(ALLOWED_HOSTS=['testserver'])
class StartKindTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة')
        cls.branch = Branch.objects.create(name='فرع', code='BR-SK', company=company)
        cls.admin = User.objects.create_user(
            username='sk_admin', password='x12345678', is_superuser=True, is_staff=True,
        )

    def _post(self, **extra):
        self.client.force_login(self.admin)
        data = {
            'name': 'موظف اختبار', 'branch': self.branch.id, 'basic_salary': '3000',
            'hire_date': '2026-10-01',
            'commencement_document': SimpleUploadedFile('c.pdf', PDF, content_type='application/pdf'),
            **extra,
        }
        return self.client.post(reverse('web:add_employee'), data)

    def test_add_page_shows_the_option(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('web:add_employee')).content.decode()
        self.assertIn('name="start_kind"', html)
        self.assertIn('عودة من إجازة', html)

    def test_default_is_new(self):
        self.assertEqual(self._post().status_code, 302)
        self.assertEqual(EmploymentRequest.objects.get().start_kind, 'new')

    def test_after_leave_is_saved(self):
        self.assertEqual(self._post(start_kind='after_leave').status_code, 302)
        req = EmploymentRequest.objects.get()
        self.assertEqual(req.start_kind, 'after_leave')
        self.assertEqual(req.get_start_kind_display(), 'عودة من إجازة')

    def test_invalid_kind_is_rejected(self):
        r = self._post(start_kind='bogus')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(EmploymentRequest.objects.exists())

    def test_detail_page_shows_kind(self):
        self._post(start_kind='after_leave')
        req = EmploymentRequest.objects.get()
        html = self.client.get(reverse('web:employment_request_detail', args=[req.id])).content.decode()
        self.assertIn('عودة من إجازة', html)
        self.assertIn('تاريخ العودة من الإجازة', html)
