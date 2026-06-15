"""اختبارات جدول الدوام — PDF وبريد."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import Branch, Company
from apps.core.services.work_schedule_context import build_schedule_boxes_context
from apps.core.services.work_schedule_pdf import build_work_schedule_pdf
from apps.employees.models import Employee
from apps.setup.models import Sponsorship


class WorkSchedulePdfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة اختبار')
        branch = Branch.objects.create(name='فرع A', code='BR-A', company=company)
        sponsorship = Sponsorship.objects.create(code='SP-SCH', company_name='كفالة')
        cls.employee = Employee.objects.create(
            name='موظف جدول',
            branch=branch,
            employee_number='1001',
            status=Employee.Status.ACTIVE,
            hire_date=date(2024, 1, 1),
            basic_salary=Decimal('3000'),
            sponsorship=sponsorship,
        )

    def test_build_schedule_boxes_context(self):
        boxes = build_schedule_boxes_context([
            {
                'year': 2026,
                'month': 6,
                'days': [1, 2, 3],
                'day_codes': {'1': '✓', '2': 'off', '3': '✓'},
                'shift_label': '8ص–4م',
            },
        ])
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0]['month_name'], 'يونيو')
        self.assertEqual(boxes[0]['days_count'], 3)
        self.assertEqual(len(boxes[0]['day_cells']), 31)
        self.assertTrue(boxes[0]['day_cells'][0]['active'])

    def test_build_work_schedule_pdf_returns_bytes(self):
        boxes = build_schedule_boxes_context([
            {
                'year': 2026,
                'month': 6,
                'days': [1],
                'day_codes': {'1': '✓'},
                'shift_label': '8ص–4م',
            },
        ])
        pdf = build_work_schedule_pdf(employee=self.employee, boxes=boxes)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 500)

    @patch('apps.core.services.work_schedule_mail.EmailMultiAlternatives.send')
    def test_send_work_schedule_email_attaches_pdf(self, mock_send):
        from apps.core.services.work_schedule_mail import send_work_schedule_email

        send_work_schedule_email(
            employee=self.employee,
            boxes_data=[{
                'year': 2026,
                'month': 6,
                'days': [1],
                'day_codes': {'1': '✓'},
                'shift_label': '8ص–4م',
            }],
            recipients=['hr@example.com'],
        )
        mock_send.assert_called_once()
