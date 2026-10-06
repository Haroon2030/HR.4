"""مرفق اختياري مع طلبات الملف السريعة (تعديل راتب، نقل، تصفية، إعادة تفعيل)."""
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Branch, Company, PendingAction
from apps.employees.models import Employee

User = get_user_model()


def _pdf(name='proof.pdf'):
    return SimpleUploadedFile(name, b'%PDF-1.4\n%test\n', content_type='application/pdf')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class QuickRequestAttachmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='B1', code='B1', company=company)
        cls.other_branch = Branch.objects.create(name='B2', code='B2', company=company)
        cls.admin = User.objects.create_superuser(username='boss', password='Pass-User-99!', email='b@e.co')
        cls.employee = Employee.objects.create(
            name='موظف', branch=cls.branch, status=Employee.Status.ACTIVE,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _latest(self, action_type):
        return PendingAction.objects.filter(
            employee=self.employee, action_type=action_type,
        ).order_by('-id').first()

    def test_salary_adjust_keeps_attachment(self):
        self.client.post(
            reverse('web:adjust_employee_salary', args=[self.employee.id]),
            {
                'new_basic_salary': '5000', 'effective_date': '2026-10-06',
                'reason': 'علاوة', 'document': _pdf(),
            },
        )
        action = self._latest('salary_adjust')
        self.assertIsNotNone(action)
        self.assertTrue(action.attachment)
        self.assertTrue(action.attachment.name.endswith('.pdf'))

    def test_transfer_keeps_attachment(self):
        self.client.post(
            reverse('web:transfer_employee', args=[self.employee.id]),
            {
                'transfer_date': '2026-10-06', 'reason': 'احتياج',
                'new_branch': self.other_branch.id, 'document': _pdf(),
            },
        )
        action = self._latest('transfer')
        self.assertIsNotNone(action)
        self.assertTrue(action.attachment)

    def test_request_without_attachment_still_works(self):
        self.client.post(
            reverse('web:adjust_employee_salary', args=[self.employee.id]),
            {'new_basic_salary': '5000', 'effective_date': '2026-10-06', 'reason': 'بدون مرفق'},
        )
        action = self._latest('salary_adjust')
        self.assertIsNotNone(action)
        self.assertFalse(action.attachment)

    def test_disallowed_file_type_is_rejected_and_no_request_created(self):
        bad = SimpleUploadedFile('virus.exe', b'MZ\x90\x00', content_type='application/octet-stream')
        self.client.post(
            reverse('web:adjust_employee_salary', args=[self.employee.id]),
            {'new_basic_salary': '5000', 'effective_date': '2026-10-06', 'reason': 'x', 'document': bad},
        )
        self.assertIsNone(self._latest('salary_adjust'))

    def test_terminate_keeps_attachment(self):
        self.client.post(
            reverse('web:terminate_employee', args=[self.employee.id]),
            {'end_date': '2026-10-06', 'end_reason': 'خارج الشركة', 'document': _pdf()},
        )
        action = self._latest('terminate')
        self.assertIsNotNone(action)
        self.assertTrue(action.attachment)
