"""اختبارات جمع وثائق قريبة الانتهاء وأمر الإشعار."""
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Branch, Company, Notification, Role, UserProfile
from apps.employees.models import Employee
from apps.employees.services.document_expiry import (
    ExpiringDocumentRow,
    collect_expiring_documents,
    document_expiry_dedupe_prefix,
)
from apps.employees.services.document_expiry_mail import send_document_expiry_summary_email
from apps.setup.models import Sponsorship

User = get_user_model()


class CollectExpiringDocumentsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة وثائق')
        cls.branch = Branch.objects.create(name='فرع 1', code='WD-1', company=cls.company)
        cls.sp = Sponsorship.objects.create(code='SP-WD', company_name='كفالة')

    def test_collects_passport_and_health_in_window(self):
        ref = date(2026, 5, 1)
        emp = Employee.objects.create(
            name='موظف وثائق',
            branch=self.branch,
            status=Employee.Status.ACTIVE,
            hire_date=date(2024, 1, 1),
            basic_salary=Decimal('4000'),
            sponsorship=self.sp,
            passport_expiry_date=ref + timedelta(days=10),
            health_card_expiry=ref + timedelta(days=5),
            residency_expiry_date=ref + timedelta(days=7),
        )
        rows = collect_expiring_documents(reference_date=ref, horizon_days=30)
        codes = {(r.employee_id, r.document_code, r.expiry_date) for r in rows}
        self.assertIn((emp.id, 'passport', emp.passport_expiry_date), codes)
        self.assertIn((emp.id, 'health_card', emp.health_card_expiry), codes)
        self.assertIn((emp.id, 'residency', emp.residency_expiry_date), codes)

    def test_excludes_terminated_and_out_of_window(self):
        ref = date(2026, 5, 1)
        Employee.objects.create(
            name='منتهي',
            branch=self.branch,
            status=Employee.Status.TERMINATED,
            hire_date=date(2020, 1, 1),
            basic_salary=Decimal('3000'),
            sponsorship=self.sp,
            passport_expiry_date=ref + timedelta(days=5),
        )
        Employee.objects.create(
            name='بعيد',
            branch=self.branch,
            status=Employee.Status.ACTIVE,
            hire_date=date(2024, 1, 1),
            basic_salary=Decimal('3000'),
            sponsorship=self.sp,
            passport_expiry_date=ref + timedelta(days=60),
        )
        rows = collect_expiring_documents(reference_date=ref, horizon_days=30)
        self.assertEqual(len(rows), 0)

    def test_dedupe_prefix_stable(self):
        p = document_expiry_dedupe_prefix(
            employee_id=7, document_code='passport', expiry_date=date(2026, 6, 1)
        )
        self.assertTrue(p.startswith('[doc_expiry:passport:7:'))


class NotifyDocumentExpiryCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة أمر')
        cls.branch = Branch.objects.create(name='فرع أ', code='CMD-A', company=cls.company)
        cls.sp = Sponsorship.objects.create(code='SP-CMD', company_name='كفالة أمر')
        role = Role.objects.create(
            name='دور اختبار تنبيه وثائق',
            role_type=Role.RoleType.HR_MANAGER,
            is_system_role=False,
        )
        cls.hr = User.objects.create_user(username='hr_doc_cmd', password='x', is_active=True)
        profile = UserProfile.objects.get(user=cls.hr)
        profile.role = role
        profile.branch = cls.branch
        profile.save(update_fields=['role', 'branch'])

    def test_dry_run_prints_without_notifications(self):
        ref = timezone.localdate()
        Employee.objects.create(
            name='للتنبيه',
            branch=self.branch,
            status=Employee.Status.ACTIVE,
            hire_date=date(2024, 1, 1),
            basic_salary=Decimal('5000'),
            sponsorship=self.sp,
            passport_expiry_date=ref + timedelta(days=3),
        )
        out = StringIO()
        call_command('notify_document_expiry', '--days=30', '--dry-run', stdout=out)
        self.assertIn('dry-run', out.getvalue())
        self.assertEqual(Notification.objects.filter(recipient=self.hr).count(), 0)

    def test_creates_notification_for_hr(self):
        ref = timezone.localdate()
        Employee.objects.create(
            name='للجرس',
            branch=self.branch,
            status=Employee.Status.ACTIVE,
            hire_date=date(2024, 1, 1),
            basic_salary=Decimal('5000'),
            sponsorship=self.sp,
            passport_expiry_date=ref + timedelta(days=2),
        )
        call_command('notify_document_expiry', '--days=30', '--cooldown-hours=0')
        self.assertTrue(
            Notification.objects.filter(recipient=self.hr, title__contains='جواز').exists()
        )


class DocumentExpiryMailTests(TestCase):
    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='from@test.com',
        DOCUMENT_EXPIRY_EMAIL_RECIPIENTS=['hr-inbox@test.com'],
    )
    def test_summary_email_one_message(self):
        rows = [
            ExpiringDocumentRow(1, 'أحمد', 'passport', 'جواز السفر', date(2026, 6, 1), 10),
        ]
        sent = send_document_expiry_summary_email(rows=rows)
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('أحمد', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['hr-inbox@test.com'])


class DocumentExpiryDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة لوحة')
        cls.branch = Branch.objects.create(name='فرع ل', code='DB-L', company=cls.company)
        cls.sp = Sponsorship.objects.create(code='SP-DB', company_name='كفالة')
        cls.admin = User.objects.create_user(
            username='super_doc_dash', password='secret123', is_superuser=True, is_staff=True
        )

    def test_dashboard_lists_row_for_superuser(self):
        ref = timezone.localdate()
        Employee.objects.create(
            name='ظاهر في اللوحة',
            branch=self.branch,
            status=Employee.Status.ACTIVE,
            hire_date=date(2024, 1, 1),
            basic_salary=Decimal('3000'),
            sponsorship=self.sp,
            passport_expiry_date=ref + timedelta(days=4),
        )
        c = Client()
        self.assertTrue(c.login(username='super_doc_dash', password='secret123'))
        url = reverse('web:document_expiry_dashboard')
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ظاهر في اللوحة')
