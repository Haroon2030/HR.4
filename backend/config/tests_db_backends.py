"""محرك MySQL بدون جداول المناطق الزمنية: إزاحات رقمية بدل أسماء المناطق."""
from django.test import SimpleTestCase

from config.db_backends.mysql.base import numeric_tz_offset


class NumericTzOffsetTests(SimpleTestCase):
    def test_named_zones(self):
        self.assertEqual(numeric_tz_offset('UTC'), '+00:00')
        self.assertEqual(numeric_tz_offset('Asia/Riyadh'), '+03:00')

    def test_explicit_offsets(self):
        self.assertEqual(numeric_tz_offset('UTC+03:00'), '+03:00')
        self.assertEqual(numeric_tz_offset('UTC-05:30'), '-05:30')
