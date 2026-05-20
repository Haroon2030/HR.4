from django.test import TestCase
from django.utils import timezone

from apps.attendance.models import AttendancePunch, BiometricDevice
from apps.attendance.services.punch_inference import (
    device_status_health,
    infer_punch_type_for_sequence,
    reclassify_punches_by_sequence,
)
from apps.core.models import Branch, Company


class PunchInferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co')
        branch = Branch.objects.create(company=company, name='فرع', code='INF-1')
        cls.device = BiometricDevice.objects.create(
            name='inf-device', ip_address='192.168.1.20', port=4370, branch=branch,
        )

    def test_infer_punch_type_alternates(self):
        self.assertEqual(
            infer_punch_type_for_sequence(0), AttendancePunch.PunchType.CHECK_IN,
        )
        self.assertEqual(
            infer_punch_type_for_sequence(1), AttendancePunch.PunchType.CHECK_OUT,
        )

    def test_device_status_health_empty(self):
        health = device_status_health(device_id=self.device.pk)
        self.assertEqual(health['total'], 0)
        self.assertFalse(health['skewed'])

    def test_reclassify_updates_sequence(self):
        base = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        for i in range(3):
            AttendancePunch.objects.create(
                device=self.device,
                device_user_id=1,
                punched_at=base + timezone.timedelta(hours=i),
                punch_type=AttendancePunch.PunchType.CHECK_IN,
                raw_status=1,
            )
        result = reclassify_punches_by_sequence(device_id=self.device.pk, dry_run=False)
        self.assertGreater(result['updated'], 0)
        types = list(
            AttendancePunch.objects.filter(device=self.device)
            .order_by('punched_at')
            .values_list('punch_type', flat=True)
        )
        self.assertEqual(types[0], AttendancePunch.PunchType.CHECK_IN)
        self.assertEqual(types[1], AttendancePunch.PunchType.CHECK_OUT)
        self.assertEqual(types[2], AttendancePunch.PunchType.CHECK_IN)
