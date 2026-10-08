"""شاشة الحضور اليومي — الوصول والفلاتر والتجميع."""
from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.attendance.models import AttendancePunch, BiometricDevice

User = get_user_model()


class AttendanceDailyScreenTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('daily_admin', 'a@example.com', 'x-pass-123')
        self.client = Client()
        self.client.force_login(self.admin)
        self.device = BiometricDevice.objects.create(
            name='جهاز الاختبار', ip_address='192.168.1.50', port=4370,
        )
        self.day = timezone.localdate()

    def _punch(self, user_id, hour, minute):
        naive = datetime(self.day.year, self.day.month, self.day.day, hour, minute)
        AttendancePunch.objects.create(
            device=self.device,
            device_user_id=user_id,
            device_user_name=f'مستخدم {user_id}',
            punched_at=timezone.make_aware(naive),
            punch_type=AttendancePunch.PunchType.CHECK_IN,
        )

    def test_page_renders_empty_day(self):
        response = self.client.get('/attendance/daily/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'لا توجد بصمات في هذا اليوم')

    def test_invalid_params_fall_back_to_defaults(self):
        response = self.client.get('/attendance/daily/?date=not-a-date&status=zzz&branch=abc')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['status'], 'all')
        self.assertEqual(response.context['day'], self.day)
        self.assertIsNone(response.context['branch_id'])

    def test_counts_and_issue_filter(self):
        self._punch(1, 8, 0)
        self._punch(1, 16, 0)
        self._punch(2, 9, 0)
        response = self.client.get('/attendance/daily/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['counts']['present'], 2)
        issues = self.client.get('/attendance/daily/?status=issues')
        self.assertTrue(all(
            r.status_label in ('بصمة واحدة', 'غير مكتمل') or not r.is_mapped
            for r in issues.context['page']
        ))

    def test_requires_report_permission(self):
        plain = User.objects.create_user('daily_plain', 'p@example.com', 'x-pass-123')
        client = Client()
        client.force_login(plain)
        self.assertEqual(client.get('/attendance/daily/').status_code, 302)
