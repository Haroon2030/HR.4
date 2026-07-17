"""فحص مسار البصمة: توقيت الرياض + منع التكرار + السحب التزايدي."""
from __future__ import annotations

import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.attendance.models import AttendancePunch, BiometricDevice, Branch
from apps.attendance.services.agent_keys import set_device_agent_key
from apps.attendance.services.ingest_signature import compute_ingest_signature
from apps.core.models import Company


@override_settings(ATTENDANCE_AGENT_API_KEY='audit-global-key-not-used')
class BiometricPipelineAuditTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='AuditCo')
        branch = Branch.objects.create(company=company, name='فرع فحص', code='AUD')
        self.device = BiometricDevice.objects.create(
            name='audit-device',
            ip_address='192.168.10.50',
            port=4370,
            branch=branch,
        )
        self.device_key = set_device_agent_key(self.device)
        self.client = APIClient()
        self.client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY=self.device_key)

    def _ingest(self, punches, *, incremental=True):
        payload = {
            'device_id': self.device.pk,
            'agent_id': 'audit-agent',
            'incremental': incremental,
            'punches': punches,
            'sync_finalize': True,
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return self.client.post(
            '/api/v1/attendance/agent/ingest/',
            data=body,
            content_type='application/json',
            HTTP_X_ATTENDANCE_SIGNATURE=compute_ingest_signature(self.device_key, body),
        )

    def test_timezone_dedup_incremental_pipeline(self):
        now = timezone.localtime().replace(microsecond=0)
        p_in = (now - timedelta(hours=8)).replace(second=0, microsecond=0)
        p_out = (now - timedelta(minutes=30)).replace(second=0, microsecond=0)
        punches = [
            {
                'device_user_id': 55,
                'punched_at': p_in.isoformat(),
                'punch_type': 'in',
                'raw_status': 0,
                'device_record_uid': 7001,
            },
            {
                'device_user_id': 55,
                'punched_at': p_out.isoformat(),
                'punch_type': 'out',
                'raw_status': 1,
                'device_record_uid': 7002,
            },
        ]

        r1 = self._ingest(punches)
        self.assertEqual(r1.status_code, 200, r1.content)
        self.assertEqual(r1.json()['data'].get('imported'), 2)

        samples = list(
            AttendancePunch.objects.filter(device=self.device).order_by('punched_at'),
        )
        self.assertEqual(len(samples), 2)
        for punch, expected in zip(samples, (p_in, p_out)):
            local = timezone.localtime(punch.punched_at)
            self.assertEqual(str(local.utcoffset()), '3:00:00')
            self.assertEqual(local.hour, expected.hour)
            self.assertEqual(local.minute, expected.minute)

        r2 = self._ingest(punches)
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()['data']
        self.assertEqual(d2.get('imported'), 0)
        self.assertGreaterEqual(
            (d2.get('skipped_duplicate') or 0) + (d2.get('skipped_time_filter') or 0),
            2,
        )
        self.assertEqual(AttendancePunch.objects.filter(device=self.device).count(), 2)

        old = p_in - timedelta(days=3)
        r3 = self._ingest([{
            'device_user_id': 55,
            'punched_at': old.isoformat(),
            'punch_type': 'in',
            'raw_status': 0,
            'device_record_uid': 7003,
        }])
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()['data'].get('imported'), 0)
        self.assertEqual(AttendancePunch.objects.filter(device=self.device).count(), 2)

        wm = self.client.get(
            '/api/v1/attendance/agent/sync-state/',
            {'device_id': self.device.pk},
        )
        self.assertEqual(wm.status_code, 200)
        self.assertIsNotNone(wm.json()['data'].get('last_punch_at'))
