"""اختبارات جدولة تقرير العمليات."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from apps.core.services.operations_report_schedule import (
    operations_report_schedule_status,
    send_time_matches_minute,
)


class OperationsReportScheduleTests(SimpleTestCase):
    @override_settings(TIME_ZONE='Asia/Riyadh')
    def test_send_time_matches_minute_same_hour_minute(self):
        now = datetime(2026, 6, 16, 8, 30, 45, tzinfo=ZoneInfo('Asia/Riyadh'))
        self.assertTrue(send_time_matches_minute(now, time(8, 30, 0)))

    @override_settings(TIME_ZONE='Asia/Riyadh')
    def test_send_time_matches_minute_different_minute(self):
        now = datetime(2026, 6, 16, 8, 31, 0, tzinfo=ZoneInfo('Asia/Riyadh'))
        self.assertFalse(send_time_matches_minute(now, time(8, 30, 0)))

    def test_schedule_status_blockers_when_disabled(self):
        class _Solo:
            is_enabled = False
            send_time = time(9, 0)
            last_sent_at = None

            def active_recipient_emails(self):
                return ['a@example.com']

        status = operations_report_schedule_status(_Solo())
        self.assertFalse(status['auto_ready'])
        self.assertIn('غير مفعّل', status['blockers'][0])
