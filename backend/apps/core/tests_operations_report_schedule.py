"""اختبارات جدولة تقرير العمليات."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from apps.core.services.operations_report_schedule import (
    operations_report_schedule_status,
    resolve_operations_report_date,
    scheduled_send_due,
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

    @override_settings(TIME_ZONE='Asia/Riyadh')
    def test_resolve_report_date_morning_is_yesterday(self):
        now = datetime(2026, 6, 19, 5, 11, 0, tzinfo=ZoneInfo('Asia/Riyadh'))
        self.assertEqual(
            resolve_operations_report_date(now, time(5, 0), manual=False),
            date(2026, 6, 18),
        )

    @override_settings(TIME_ZONE='Asia/Riyadh')
    def test_resolve_report_date_afternoon_is_today(self):
        now = datetime(2026, 6, 19, 14, 0, 0, tzinfo=ZoneInfo('Asia/Riyadh'))
        self.assertEqual(
            resolve_operations_report_date(now, time(12, 0), manual=False),
            date(2026, 6, 19),
        )

    @override_settings(TIME_ZONE='Asia/Riyadh')
    def test_scheduled_send_catch_up_after_missed_minute(self):
        class _Solo:
            send_time = time(5, 0)
            last_sent_at = None

        now = datetime(2026, 6, 19, 5, 11, 0, tzinfo=ZoneInfo('Asia/Riyadh'))
        due, reason = scheduled_send_due(now, _Solo())
        self.assertTrue(due)
        self.assertEqual(reason, 'catch_up')

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

    @override_settings(TIME_ZONE='Asia/Riyadh')
    def test_schedule_status_next_send_today(self):
        class _Solo:
            is_enabled = True
            send_time = time(21, 50)
            last_sent_at = None

            def active_recipient_emails(self):
                return ['a@example.com']

        with self.settings(TIME_ZONE='Asia/Riyadh'):
            from unittest.mock import patch

            from django.utils import timezone as dj_tz

            fixed = datetime(2026, 6, 17, 21, 40, 0, tzinfo=ZoneInfo('Asia/Riyadh'))
            with patch.object(dj_tz, 'localtime', return_value=fixed):
                status = operations_report_schedule_status(_Solo())
        self.assertTrue(status['auto_ready'])
        self.assertEqual(status['next_send_at'].hour, 21)
        self.assertEqual(status['next_send_at'].minute, 50)
        self.assertEqual(status['next_send_at'].date().isoformat(), '2026-06-17')
