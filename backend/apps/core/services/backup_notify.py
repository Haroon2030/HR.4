"""إرسال تنبيهات بريد عند انتهاء النسخ الاحتياطي لقاعدة البيانات."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def backup_notification_recipients() -> list[str]:
    emails = getattr(settings, 'BACKUP_NOTIFY_RECIPIENTS', None) or []
    return [e for e in emails if e]


def send_backup_notification(
    *,
    success: bool,
    subject_hint: str,
    body_lines: list[str],
) -> None:
    """
    لا تُفعّل إلا إذا BACKUP_NOTIFY_RECIPIENTS غير فارغ ومُفعّل في الإعدادات.
    لا تُرمي أي استثناء للمتصل — أخطاء البريد تُسجّل فقط.
    """
    recipients = backup_notification_recipients()
    if not recipients:
        return

    if success:
        if not getattr(settings, 'BACKUP_NOTIFY_ON_SUCCESS', True):
            return
    else:
        if not getattr(settings, 'BACKUP_NOTIFY_ON_FAILURE', True):
            return

    subject = subject_hint
    body = '\n'.join(body_lines)
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception('فشل إرسال بريد تنبيه النسخ الاحتياطي إلى %s', recipients)
