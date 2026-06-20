"""مطابقة وقت إرسال تقرير العمليات."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

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


def resolve_operations_report_date(
    now: datetime,
    send_time: time | None,
    *,
    manual: bool = False,
) -> date:
    """
    تاريخ محتوى التقرير.
    الإرسال المجدول قبل ظهراً: تقرير أمس (ملخص يوم كامل).
    الإرسال المجدول ظهراً فما بعد: تقرير اليوم.
    الاختبار اليدوي: اليوم الحالي.
    """
    if manual:
        return now.date()
    target = normalize_send_time(send_time)
    if target.hour < 12:
        return now.date() - timedelta(days=1)
    return now.date()


def scheduled_send_due(
    now: datetime,
    settings_obj,
    *,
    force: bool = False,
    catch_up_hours: int = 6,
) -> tuple[bool, str]:
    """
    هل حان إرسال التقرير المجدول؟
    يُرجع (due, reason) — reason للسجلات والتشخيص.
    """
    if force:
        return True, 'force'

    target = normalize_send_time(getattr(settings_obj, 'send_time', None))
    send_dt = datetime.combine(now.date(), target, tzinfo=now.tzinfo)

    if send_time_matches_minute(now, target):
        last = getattr(settings_obj, 'last_sent_at', None)
        if last:
            last_local = timezone.localtime(last)
            if (
                last_local.date() == now.date()
                and last_local.hour == now.hour
                and last_local.minute == now.minute
            ):
                return False, 'already_sent_this_minute'
        return True, 'exact_minute'

    if now < send_dt:
        return False, 'before_send_time'

    last = getattr(settings_obj, 'last_sent_at', None)
    if last and timezone.localtime(last).date() >= now.date():
        return False, 'already_sent_today'

    if now <= send_dt + timedelta(hours=catch_up_hours):
        return True, 'catch_up'

    return False, 'missed_send_window'


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
    phones = settings_obj.active_recipient_phones() if hasattr(settings_obj, 'active_recipient_phones') else []
    whatsapp_enabled = bool(getattr(settings_obj, 'send_via_whatsapp', False))
    last_sent = getattr(settings_obj, 'last_sent_at', None)
    last_sent_local = timezone.localtime(last_sent) if last_sent else None
    report_date = resolve_operations_report_date(now, send_at, manual=False)
    due, due_reason = scheduled_send_due(now, settings_obj)
    next_send = None
    if enabled:
        candidate = datetime.combine(now.date(), send_at, tzinfo=now.tzinfo)
        if now >= candidate:
            candidate += timedelta(days=1)
        next_send = candidate

    return {
        'timezone': tz_name,
        'server_now': now,
        'send_time': send_at,
        'send_time_label': format_send_time(send_at),
        'report_date': report_date,
        'is_enabled': enabled,
        'recipient_count': len(recipients),
        'whatsapp_recipient_count': len(phones),
        'send_via_whatsapp': whatsapp_enabled,
        'time_matches_now': send_time_matches_minute(now, send_at),
        'scheduled_due_now': due,
        'scheduled_due_reason': due_reason,
        'last_sent_at': last_sent_local,
        'next_send_at': next_send,
        'auto_ready': enabled and (bool(recipients) or (whatsapp_enabled and bool(phones))),
        'blockers': [
            *( [] if enabled else ['الإرسال التلقائي غير مفعّل — فعّله واحفظ الإعدادات.'] ),
            *( [] if recipients or (whatsapp_enabled and phones) else ['لا يوجد بريد أو جوال واتساب محفوظ.'] ),
            *( [] if not whatsapp_enabled or phones else ['واتساب مفعّل — أضف رقماً واحداً على الأقل.'] ),
        ],
    }
