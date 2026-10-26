"""زر «استعراض الملف المرفوع» في جدول إجازات الموظف."""
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.core.models import Branch, Company
from apps.employees.models import Employee, EmployeeLeave

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LeaveDocumentButtonTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user('leavedoc', password='x', is_superuser=True, is_staff=True)
        company = Company.objects.create(name='شركة الإجازات')
        branch = Branch.objects.create(name='فرع الإجازات', code='LD1', company=company)
        self.emp = Employee.objects.create(
            name='موظف إجازة', hire_date=date.today() - timedelta(days=500),
            basic_salary=Decimal('3000'), branch=branch,
        )
        self.client = Client()
        self.client.force_login(admin)

    def _leave(self, with_document):
        document = (
            SimpleUploadedFile('sick.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')
            if with_document else None
        )
        return EmployeeLeave.objects.create(
            employee=self.emp, leave_type='annual',
            date_from=date.today() - timedelta(days=10), date_to=date.today() - timedelta(days=5),
            days=Decimal('6'), notes='', document=document,
        )

    def _page(self):
        return self.client.get(reverse('web:view_employee', args=[self.emp.id]) + '?tab=leaves')

    def test_button_shown_for_leave_with_file_even_without_notes(self):
        leave = self._leave(with_document=True)
        page = self._page()
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'استعراض الملف المرفوع')
        self.assertContains(page, f'data-hr-media-url="{leave.document.url}"')

    def test_button_hidden_when_no_file(self):
        self._leave(with_document=False)
        self.assertNotContains(self._page(), 'استعراض الملف المرفوع')


class SickLeaveSummaryTests(TestCase):
    def setUp(self):
        from datetime import date
        company = Company.objects.create(name='شركة المرضية')
        branch = Branch.objects.create(name='فرع المرضية', code='SK1', company=company)
        self.emp = Employee.objects.create(
            name='موظف مرضي', hire_date=date(2024, 1, 1), basic_salary=Decimal('3000'), branch=branch,
        )

    def _leave(self, leave_type, start, days):
        return EmployeeLeave.objects.create(
            employee=self.emp, leave_type=leave_type, date_from=start,
            date_to=start + timedelta(days=int(days) - 1), days=Decimal(days),
        )

    def test_counts_only_sick_leaves_and_splits_current_year(self):
        from apps.employees.services.employee_view_data import sick_leave_summary
        self._leave('sick', date(2026, 3, 1), '5')
        self._leave('sick', date(2025, 6, 1), '3')
        self._leave('annual', date(2026, 4, 1), '10')  # لا تُحتسب
        summary = sick_leave_summary(self.emp, today=date(2026, 10, 1))
        self.assertEqual(summary['count'], 2)
        self.assertEqual(summary['days'], Decimal('8'))
        self.assertEqual(summary['year_days'], Decimal('5'))
        self.assertEqual(summary['year'], 2026)

    def test_no_sick_leaves_gives_zeros(self):
        from apps.employees.services.employee_view_data import sick_leave_summary
        summary = sick_leave_summary(self.emp, today=date(2026, 10, 1))
        self.assertEqual((summary['count'], summary['days'], summary['year_days']), (0, Decimal('0'), Decimal('0')))
