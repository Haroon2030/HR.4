from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.attendance.models import AttendancePunch, BiometricDevice, Branch
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
        self.client = APIClient()

    def test_ingest_requires_key(self):
        anon = APIClient()
        r = anon.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': self.device.pk, 'punches': []},
            format='json',
        )
        self.assertIn(r.status_code, (401, 403))

    def test_ingest_imports_punch(self):
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
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
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
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
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
        r = client.get('/api/v1/attendance/agent/devices/')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()['data']), 1)

    def test_pull_requests_queue_and_ack(self):
        from apps.attendance.services.agent_pull_queue import (
            get_pull_request,
            queue_pull_request,
        )

        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
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
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': self.device.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_pull_requests_ack_requires_device_id(self):
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
        response = client.post(
            '/api/v1/attendance/agent/pull-requests/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_ingest_unknown_device_returns_404(self):
        client = APIClient()
        client.credentials(HTTP_X_ATTENDANCE_AGENT_KEY='test-agent-key-secret')
        response = client.post(
            '/api/v1/attendance/agent/ingest/',
            {'device_id': 999999, 'punches': []},
            format='json',
        )
        self.assertEqual(response.status_code, 404)
