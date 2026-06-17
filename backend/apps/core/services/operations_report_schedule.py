"""مطابقة وقت إرسال تقرير العمليات."""
from __future__ import annotations

from datetime import datetime, time

from django.conf import settings
from django.utils import timezone


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


def operations_report_schedule_status(settings_obj) -> dict:
    """ملخص حالة الجدولة للواجهة والتشخيص."""
    now = timezone.localtime()
    tz_name = settings.TIME_ZONE
    send_at = normalize_send_time(getattr(settings_obj, 'send_time', None))
    enabled = bool(getattr(settings_obj, 'is_enabled', False))
    recipients = settings_obj.active_recipient_emails() if hasattr(settings_obj, 'active_recipient_emails') else []
    last_sent = getattr(settings_obj, 'last_sent_at', None)
    last_sent_local = timezone.localtime(last_sent) if last_sent else None

    return {
        'timezone': tz_name,
        'server_now': now,
        'send_time': send_at,
        'send_time_label': format_send_time(send_at),
        'is_enabled': enabled,
        'recipient_count': len(recipients),
        'time_matches_now': send_time_matches_minute(now, send_at),
        'last_sent_at': last_sent_local,
        'auto_ready': enabled and bool(recipients),
        'blockers': [
            *( [] if enabled else ['الإرسال التلقائي غير مفعّل — فعّله واحفظ الإعدادات.'] ),
            *( [] if recipients else ['لا يوجد بريد مستلم محفوظ.'] ),
        ],
    }
