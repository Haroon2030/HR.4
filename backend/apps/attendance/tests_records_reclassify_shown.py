"""ترتيب الدخول/الخروج يعمل على السجلات الظاهرة بعد الفلترة، بدون اختيار جهاز."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import AttendancePunch, BiometricDevice
from apps.core.models import Branch, Company

User = get_user_model()
IN = AttendancePunch.PunchType.CHECK_IN
OUT = AttendancePunch.PunchType.CHECK_OUT


class ReclassifyShownRowsTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='Co-RC')
        branch = Branch.objects.create(company=company, name='فرع RC', code='RC-1')
        self.device = BiometricDevice.objects.create(
            name='rc-device', ip_address='192.168.1.31', port=4370, branch=branch,
        )
        self.admin = User.objects.create_superuser(username='rc_admin', password='x-pass-123')
        self.client.force_login(self.admin)
        base = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        # موظف 1 و 2 على نفس الجهاز، كل واحد 3 بصمات في يوم واحد — كلها مُصنّفة دخولاً (خطأ)
        for uid in (1, 2):
            for i in range(3):
                AttendancePunch.objects.create(
                    device=self.device, device_user_id=uid,
                    punched_at=base + timezone.timedelta(hours=i),
                    punch_type=IN, raw_status=1,
                )

    def _types(self, uid):
        return list(
            AttendancePunch.objects.filter(device=self.device, device_user_id=uid)
            .order_by('punched_at').values_list('punch_type', flat=True)
        )

    def test_sorts_only_the_filtered_user_without_choosing_a_device(self):
        resp = self.client.post(reverse('web:attendance_records_reclassify') + '?device_user=1')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._types(1), [IN, OUT, IN])
        self.assertEqual(self._types(2), [IN, IN, IN])  # خارج الفلتر — لم يُمسّ

    def test_punch_type_filter_does_not_break_the_sequence(self):
        # فلتر «دخول فقط» يجب ألا يقطع التسلسل: يبقى ترتيب كل بصمات اليوم صحيحاً
        self.client.post(reverse('web:attendance_records_reclassify') + '?device_user=1&punch_type=in')
        self.assertEqual(self._types(1), [IN, OUT, IN])

    def test_no_filter_sorts_every_shown_row(self):
        self.client.post(reverse('web:attendance_records_reclassify'))
        self.assertEqual(self._types(1), [IN, OUT, IN])
        self.assertEqual(self._types(2), [IN, OUT, IN])

    def test_redirects_back_with_the_same_filters(self):
        resp = self.client.post(reverse('web:attendance_records_reclassify') + '?device_user=1&from=2026-10-01')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('device_user=1', resp['Location'])
        self.assertIn('from=2026-10-01', resp['Location'])

    def test_empty_filter_reports_nothing_to_sort(self):
        resp = self.client.post(reverse('web:attendance_records_reclassify') + '?device_user=999', follow=True)
        self.assertContains(resp, 'لا توجد سجلات بصمة في الفلتر الحالي')

    def test_button_visible_in_toolbar_and_old_device_prompt_gone(self):
        resp = self.client.get(reverse('web:attendance_records'))
        html = resp.content.decode()
        self.assertIn('ترتيب دخول/خروج', html)
        self.assertNotIn('يجب اختيار جهاز بصمة', html)
