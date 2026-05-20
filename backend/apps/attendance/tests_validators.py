from django.test import TestCase, override_settings
from unittest.mock import MagicMock

from apps.attendance.validators import (
    cloud_pull_blocked_message,
    is_private_lan_ip,
    validate_device_ipv4,
)


class DeviceIPv4ValidatorTests(TestCase):
    def test_valid_ipv4(self):
        self.assertEqual(validate_device_ipv4('192.168.1.10'), '192.168.1.10')

    def test_empty_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_device_ipv4('')
        self.assertIn('مطلوب', str(ctx.exception))

    def test_invalid_raises_arabic_message(self):
        with self.assertRaises(ValueError) as ctx:
            validate_device_ipv4('not-an-ip')
        self.assertIn('غير صالح', str(ctx.exception))

    def test_ipv6_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_device_ipv4('2001:db8::1')
        self.assertIn('IPv4', str(ctx.exception))


class PrivateLanAndCloudPullTests(TestCase):
    def test_is_private_lan(self):
        self.assertTrue(is_private_lan_ip('10.0.0.5'))
        self.assertFalse(is_private_lan_ip('8.8.8.8'))

    @override_settings(BIOMETRIC_MOCK_MODE=False)
    def test_cloud_pull_blocked_for_private_lan(self):
        device = MagicMock()
        device.name = 'جهاز الفرع'
        device.ip_address = '192.168.0.50'
        device.pk = 3
        msg = cloud_pull_blocked_message(device)
        self.assertIsNotNone(msg)
        self.assertIn('شبكة محلية', msg)

    @override_settings(BIOMETRIC_MOCK_MODE=True)
    def test_mock_mode_skips_cloud_block(self):
        device = MagicMock()
        device.ip_address = '192.168.0.50'
        self.assertIsNone(cloud_pull_blocked_message(device))
