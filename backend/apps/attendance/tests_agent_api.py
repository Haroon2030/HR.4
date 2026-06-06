import json

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.attendance.models import AttendanceIngestLog, AttendancePunch, BiometricDevice, Branch
from apps.attendance.services.ingest_signature import compute_ingest_signature
from apps.core.models import Company


@override_settings(ATTENDANCE_AGENT_API_KEY='test-agent-key-secret')
class AttendanceAgentAPITests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='Co')
        branch = Branch.objects.create(company=company, name='فرع', code='BR1')
        self.device = BiometricDevice.objects.create(
            name='test-device',
            ip_address='192.168.1.50',
            port=4370,
            branch=branch,
        )
        from apps.attendance.services.agent_keys import set_device_agent_key

        self.device_key = set_device_agent_key(self.device)
        self.client = APIClient()

    def _device_client(self):
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY=self.device_key)
        return client

    def _signed_ingest_post(self, client, payload, *, api_key=None):
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        key = api_key or self.device_key
        return client.post(
            '/api/v1/attendance/agent/ingest/',
            data=body,
            content_type='application/json',
            HTTP_X_ATTENDANCE_SIGNATURE=compute_ingest_signature(key, body),
        )

    def test_ingest_requires_key(self):
        anon = APIClient()
        r = anon.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': self.device.pk, 'punches': []},
            format='json',
        )
        self.assertIn(r.status_code, (401, 403))

    def test_ingest_imports_punch(self):
        client = self._device_client()
        ts = timezone.now().replace(microsecond=0)
        r = client.post(
            '/api/v1/attendance/agent/ingest/',
            {
                'device_id': self.device.pk,
                'agent_id': 'test-agent',
                'punches': [{
                    'device_user_id': 9,
                    'punched_at': ts.isoformat(),
                    'punch_type': 'in',
                    'device_record_uid': 9001,
                }],
            },
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['success'])
        self.assertEqual(AttendancePunch.objects.filter(device=self.device).count(), 1)

    def test_ingest_skips_duplicate(self):
        client = self._device_client()
        ts = timezone.now().replace(microsecond=0)
        payload = {
            'device_id': self.device.pk,
            'punches': [{
                'device_user_id': 9,
                'punched_at': ts.isoformat(),
                'punch_type': 'in',
                'device_record_uid': 9002,
            }],
        }
        client.post(
            '/api/v1/attendance/agent/ingest/',
            payload,
            format='json',
        )
        r2 = client.post(
            '/api/v1/attendance/agent/ingest/',
            payload,
            format='json',
        )
        self.assertEqual(r2.json()['data']['imported'], 0)
        self.assertEqual(AttendancePunch.objects.filter(device=self.device).count(), 1)

    def test_list_devices(self):
        client = self._device_client()
        r = client.get('/api/v1/attendance/agent/devices/')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()['data']), 1)

    def test_pull_requests_queue_and_ack(self):
        from apps.attendance.services.agent_pull_queue import (
            get_pull_request,
            queue_pull_request,
        )

        client = self._device_client()
        queue_pull_request(self.device.pk, requested_by_id=1)

        r = client.get('/api/v1/attendance/agent/pull-requests/')
        self.assertEqual(r.status_code, 200)
        data = r.json()['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['device_id'], self.device.pk)

        r2 = client.post(
            '/api/v1/attendance/agent/pull-requests/',
            {'device_id': self.device.pk},
            format='json',
        )
        self.assertEqual(r2.status_code, 200)
        self.assertIsNone(get_pull_request(self.device.pk))

    def test_ingest_invalid_payload_returns_400(self):
        client = self._device_client()
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': self.device.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_pull_requests_ack_requires_device_id(self):
        client = self._device_client()
        response = client.post(
            '/api/v1/attendance/agent/pull-requests/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_ingest_unknown_device_returns_404(self):
        client = self._device_client()
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': 999999, 'punches': []},
            format='json',
        )
        # مفتاح الجهاز يُرفض قبل البحث عن جهاز غير موجود
        self.assertIn(response.status_code, (403, 404))

    def test_device_key_cannot_ingest_other_device(self):
        branch = self.device.branch
        other = BiometricDevice.objects.create(
            name='other-device',
            ip_address='192.168.1.51',
            port=4370,
            branch=branch,
        )
        from apps.attendance.services.agent_keys import set_device_agent_key

        device_key = set_device_agent_key(self.device)
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY=device_key)
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': other.pk, 'punches': []},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(DEBUG=False, AGENT_GLOBAL_KEY_LIST_DEVICES=False)
    def test_global_key_cannot_ingest_in_production_mode(self):
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': self.device.pk, 'punches': []},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(DEBUG=False, AGENT_GLOBAL_KEY_LIST_DEVICES=False)
    def test_global_key_cannot_list_devices_in_production_mode(self):
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
        response = client.get('/api/v1/attendance/agent/devices/')
        self.assertEqual(response.status_code, 403)

    def test_ingest_rejects_punch_too_far_in_past(self):
        from datetime import timedelta

        client = self._device_client()
        old_ts = (timezone.now() - timedelta(days=120)).replace(microsecond=0)
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {
                'device_id': self.device.pk,
                'punches': [{
                    'device_user_id': 1,
                    'punched_at': old_ts.isoformat(),
                    'punch_type': 'in',
                    'device_record_uid': 88001,
                }],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_device_key_ingest_own_device(self):
        from apps.attendance.services.agent_keys import set_device_agent_key

        device_key = set_device_agent_key(self.device)
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY=device_key)
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': self.device.pk, 'punches': []},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    @override_settings(ATTENDANCE_REQUIRE_INGEST_SIGNATURE=True)
    def test_ingest_rejects_missing_signature_when_required(self):
        client = self._device_client()
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': self.device.pk, 'punches': []},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            AttendanceIngestLog.objects.filter(
                status=AttendanceIngestLog.Status.REJECTED_SIGNATURE,
            ).count(),
            1,
        )

    @override_settings(ATTENDANCE_REQUIRE_INGEST_SIGNATURE=True)
    def test_ingest_rejects_invalid_signature(self):
        client = self._device_client()
        payload = {'device_id': self.device.pk, 'punches': []}
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            data=body,
            content_type='application/json',
            HTTP_X_ATTENDANCE_SIGNATURE='sha256=deadbeef',
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(ATTENDANCE_REQUIRE_INGEST_SIGNATURE=True)
    def test_ingest_accepts_valid_signature(self):
        client = self._device_client()
        ts = timezone.now().replace(microsecond=0)
        response = self._signed_ingest_post(client, {
            'device_id': self.device.pk,
            'agent_id': 'signed-agent',
            'punches': [{
                'device_user_id': 42,
                'punched_at': ts.isoformat(),
                'punch_type': 'in',
                'device_record_uid': 42001,
            }],
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        log = AttendanceIngestLog.objects.get(status=AttendanceIngestLog.Status.SUCCESS)
        self.assertTrue(log.signature_valid)
        self.assertEqual(log.imported, 1)

    def test_ingest_creates_audit_log_on_success(self):
        client = self._device_client()
        client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': self.device.pk, 'punches': []},
            format='json',
        )
        self.assertEqual(
            AttendanceIngestLog.objects.filter(
                status=AttendanceIngestLog.Status.SUCCESS,
                device=self.device,
            ).count(),
            1,
        )
