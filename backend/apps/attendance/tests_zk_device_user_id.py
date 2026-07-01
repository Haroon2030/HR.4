from django.test import SimpleTestCase

from apps.attendance.services.zk_device_user_id import parse_device_user_id


class ParseDeviceUserIdTests(SimpleTestCase):
    def test_plain_integer(self):
        self.assertEqual(parse_device_user_id(2525), 2525)

    def test_digit_string(self):
        self.assertEqual(parse_device_user_id('42'), 42)

    def test_corrupted_zk_string(self):
        self.assertEqual(
            parse_device_user_id('2525 FID=10 RETRY=3 OVE'),
            2525,
        )

    def test_uid_fallback(self):
        self.assertEqual(parse_device_user_id('bad', uid_fallback=7), 7)

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_device_user_id('FID=10 RETRY=3'))
