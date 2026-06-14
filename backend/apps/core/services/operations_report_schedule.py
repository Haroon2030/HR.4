"""مطابقة وقت إرسال تقرير العمليات."""
from __future__ import annotations

from datetime import datetime, time


def normalize_send_time(value: time | None) -> time:
    if value is None:
        return time(12, 0, 0)
    return value


def send_time_matches_now(now: datetime, send_time: time | None) -> bool:
    """يطابق الساعة والدقيقة والثواني (للاستخدام مع cron كل دقيقة)."""
    target = normalize_send_time(send_time)
    return (
        now.hour == target.hour
        and now.minute == target.minute
        and now.second == target.second
    )


def send_time_matches_minute(now: datetime, send_time: time | None) -> bool:
    """يطابق الساعة والدقيقة (cron يعمل كل دقيقة)."""
    target = normalize_send_time(send_time)
    return now.hour == target.hour and now.minute == target.minute


def format_send_time(send_time: time | None) -> str:
    target = normalize_send_time(send_time)
    return target.strftime('%H:%M:%S')
