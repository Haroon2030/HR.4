"""اختبارات طابور سحب البصمة (قاعدة البيانات)."""
from django.test import TestCase

from apps.attendance.models import BiometricDevice, BiometricPullRequest, Branch
from apps.attendance.services.agent_pull_queue import (
    acknowledge_pull_request,
    list_pending_pull_requests,
    queue_lan_device_sync,
    queue_pull_request,
)
from apps.attendance.validators import is_private_lan_ip
from apps.core.models import Company


class BiometricPullQueueTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='Co')
        branch = Branch.objects.create(company=company, name='فرع', code='BR1')
        self.device = BiometricDevice.objects.create(
            name='LAN Device',
            ip_address='192.168.1.55',
            port=4370,
            branch=branch,
        )

    def test_queue_persists_in_database(self):
        queue_pull_request(self.device.pk)
        self.assertEqual(BiometricPullRequest.objects.filter(
            device=self.device, acknowledged_at__isnull=True,
        ).count(), 1)
        pending = list_pending_pull_requests()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['device_id'], self.device.pk)

    def test_acknowledge_clears_pending(self):
        queue_pull_request(self.device.pk)
        acknowledge_pull_request(self.device.pk)
        self.assertEqual(list_pending_pull_requests(), [])

    def test_lan_sync_requires_agent_key(self):
        self.assertTrue(is_private_lan_ip(self.device.ip_address))
        queued, msg = queue_lan_device_sync(self.device)
        self.assertFalse(queued)
        self.assertIn('مفتاح وكيل', msg)

    def test_lan_sync_queues_when_key_present(self):
        from apps.attendance.services.agent_keys import set_device_agent_key

        set_device_agent_key(self.device)
        queued, msg = queue_lan_device_sync(self.device)
        self.assertTrue(queued)
        self.assertIn('طلب مزامنة', msg)

    def test_list_pending_filtered_by_device(self):
        company = Company.objects.create(name='Co2')
        branch = Branch.objects.create(company=company, name='B2', code='BR2')
        other = BiometricDevice.objects.create(
            name='Other',
            ip_address='192.168.1.56',
            port=4370,
            branch=branch,
        )
        queue_pull_request(self.device.pk)
        queue_pull_request(other.pk)
        filtered = list_pending_pull_requests(device_id=self.device.pk)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['device_id'], self.device.pk)
