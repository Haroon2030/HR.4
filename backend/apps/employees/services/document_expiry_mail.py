"""بريد اختياري لتلخيص وثائق تنتهي قريباً (أمر notify_document_expiry --send-email)."""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

from apps.core.models import Role
from apps.employees.services.document_expiry import ExpiringDocumentRow

logger = logging.getLogger(__name__)


def document_expiry_email_recipients() -> list[str]:
    """
    عناوين المستلمين:
    - إن وُجدت DOCUMENT_EXPIRY_EMAIL_RECIPIENTS تُستخدم وحدها.
    - وإلا: بريد المستخدمين النشطين بدور admin أو hr_manager (إن وُجد بريد).
    """
    explicit = getattr(settings, 'DOCUMENT_EXPIRY_EMAIL_RECIPIENTS', None) or []
    cleaned = [e.strip() for e in explicit if e and str(e).strip()]
    if cleaned:
        return list(dict.fromkeys(cleaned))

    User = get_user_model()
    emails = (
        User.objects.filter(
            is_active=True,
            email__gt='',
            profile__role__role_type__in=[
                Role.RoleType.ADMIN,
                Role.RoleType.HR_MANAGER,
            ],
        )
        .values_list('email', flat=True)
        .distinct()
    )
    return list(dict.fromkeys(e.strip() for e in emails if e and e.strip()))


def send_document_expiry_summary_email(*, rows: list[ExpiringDocumentRow]) -> int:
    """
    يرسل رسالة واحدة بجميع الصفوف. يُرجع عدد الرسائل المُرسَلة فعلياً (0 أو 1).

    أخطاء SMTP تُسجَّل فقط ولا تُرفع للمتصل.
    """
    if not rows:
        return 0

    recipients = document_expiry_email_recipients()
    if not recipients:
        logger.info('تخطي بريد انتهاء الوثائق: لا مستلمين (DOCUMENT_EXPIRY_EMAIL_RECIPIENTS أو بريد مديري الموارد).')
        return 0

    lines = [
        'تنبيه: وثائق موظفين تنتهي ضمن النافذة المحددة.',
        '────────────────────────────────────',
    ]
    for r in rows:
        lines.append(
            f'- [{r.document_label}] {r.employee_name} (id={r.employee_id}) — '
            f'انتهاء {r.expiry_date} (خلال {r.days_until} يوماً)'
        )
    body = '\n'.join(lines)
    subject = f'[{settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "HR"}] وثائق تنتهي قريباً ({len(rows)})'

    try:
        send_mail(
            subject=subject[:998],
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        return 1
    except Exception:
        logger.exception('فشل إرسال بريد ملخص انتهاء الوثائق إلى %s', recipients)
        return 0
