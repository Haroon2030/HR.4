"""اختبارات خدمة تقييم حضور البصمة."""
from __future__ import annotations

from datetime import date, datetime, time
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.attendance.models import AttendancePunch, EmployeeBiometricSettings
from apps.attendance.services.attendance_evaluation import (
    checkin_cutoff,
    evaluate_daily_checkin,
    evaluate_daily_checkout,
    punch_counts_as_late_entry,
)


def _settings(
    *,
    expected_check_in: time | None = time(8, 0),
    expected_check_out: time | None = None,
    late_grace_minutes: int = 30,
) -> EmployeeBiometricSettings:
    return EmployeeBiometricSettings(
        expected_check_in=expected_check_in,
        expected_check_out=expected_check_out,
        late_grace_minutes=late_grace_minutes,
    )


def _aware(day: date, t: time) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, t), tz)


class AttendanceEvaluationTests(TestCase):
    def setUp(self):
        self.day = timezone.localdate()

    def test_on_time_checkin_within_grace(self):
        result = evaluate_daily_checkin(
            self.day,
            _aware(self.day, time(8, 0)),
            _settings(),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.is_late)
        self.assertEqual(result.late_minutes, 0)
        self.assertEqual(result.late_after_grace_minutes, 0)

    def test_late_checkin_one_minute_after_grace(self):
        result = evaluate_daily_checkin(
            self.day,
            _aware(self.day, time(8, 31)),
            _settings(),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.is_late)
        self.assertEqual(result.late_minutes, 31)
        self.assertEqual(result.late_after_grace_minutes, 1)

    def test_late_checkin_sixty_minutes_total_thirty_after_grace(self):
        result = evaluate_daily_checkin(
            self.day,
            _aware(self.day, time(9, 0)),
            _settings(),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.is_late)
        self.assertEqual(result.late_minutes, 60)
        self.assertEqual(result.late_after_grace_minutes, 30)

    def test_no_expected_check_in_returns_none(self):
        result = evaluate_daily_checkin(
            self.day,
            _aware(self.day, time(9, 0)),
            _settings(expected_check_in=None),
        )
        self.assertIsNone(result)

    def test_early_checkout(self):
        result = evaluate_daily_checkout(
            self.day,
            _aware(self.day, time(16, 0)),
            _settings(expected_check_out=time(17, 0)),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.is_early)
        self.assertEqual(result.early_minutes, 60)

    def test_on_time_checkout(self):
        result = evaluate_daily_checkout(
            self.day,
            _aware(self.day, time(17, 30)),
            _settings(expected_check_out=time(17, 0)),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.is_early)

    def test_punch_counts_as_late_entry_for_unknown_type(self):
        settings = _settings()
        punch = MagicMock(spec=AttendancePunch)
        punch.punch_type = AttendancePunch.PunchType.UNKNOWN
        punch.punched_at = _aware(self.day, time(9, 0))
        self.assertTrue(punch_counts_as_late_entry(punch, settings))

    def test_punch_not_late_before_cutoff(self):
        settings = _settings()
        punch = MagicMock(spec=AttendancePunch)
        punch.punch_type = AttendancePunch.PunchType.CHECK_IN
        punch.punched_at = _aware(self.day, time(8, 15))
        self.assertFalse(punch_counts_as_late_entry(punch, settings))

    def test_checkin_cutoff_matches_grace(self):
        cutoff = checkin_cutoff(self.day, time(8, 0), 30)
        self.assertEqual(timezone.localtime(cutoff).time(), time(8, 30))
