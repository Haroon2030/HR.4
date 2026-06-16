"""حالة إرسال البريد الفعلي (SMTP مقابل وضع التطوير)."""
from __future__ import annotations

import logging
import re
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class SmtpNotConfiguredError(Exception):
    """SMTP غير مضبوط — لا يُرسل بريد حقيقي."""


class SmtpConnectionError(Exception):
    """فشل الاتصال أو المصادقة مع SMTP."""


def email_delivery_mode() -> str:
    backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').lower()
    if 'console' in backend:
        return 'console'
    if 'locmem' in backend:
        return 'locmem'
    if 'filebased' in backend:
        return 'file'
    if 'dummy' in backend:
        return 'dummy'
    if 'smtp' in backend:
        return 'smtp'
    return 'other'


def is_real_smtp_delivery() -> bool:
    """True فقط عند ضبط SMTP فعلي — وليس console/locmem/file/dummy."""
    if email_delivery_mode() != 'smtp':
        return False
    return bool((getattr(settings, 'EMAIL_HOST', '') or '').strip())


def email_delivery_status() -> dict:
    mode = email_delivery_mode()
    smtp_ready = is_real_smtp_delivery()
    from_warning = from_email_smtp_mismatch_warning()
    return {
        'mode': mode,
        'smtp_ready': smtp_ready,
        'backend': getattr(settings, 'EMAIL_BACKEND', ''),
        'host': (getattr(settings, 'EMAIL_HOST', '') or '').strip(),
        'from_email': (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip(),
        'effective_from': resolve_from_email(),
        'from_warning': from_warning,
    }


def _extract_email_address(raw: str) -> str:
    value = (raw or '').strip()
    match = re.search(r'<([^>]+)>', value)
    if match:
        return match.group(1).strip()
    return value


def _extract_display_name(raw: str) -> str:
    value = (raw or '').strip()
    match = re.match(r'^["\']?(.+?)["\']?\s*<[^>]+>\s*$', value)
    if match:
        return match.group(1).strip()
    if value and '@' not in value:
        return value
    return ''


def resolve_from_email() -> str:
    """
    يربط From بحساب SMTP المصادَق عليه.
    Hostinger (وغيره) قد يقبل SMTP ثم لا يُسلّم خارجياً إذا اختلف المرسل عن EMAIL_HOST_USER.
    """
    user = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip()
    default = (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip()
    if not user:
        return default or 'noreply@localhost'
    display = _extract_display_name(default)
    if display:
        return f'{display} <{user}>'
    return user


def prepare_outbound_message(message: Any) -> Any:
    """يضبط From/Reply-To قبل الإرسال."""
    resolved_from = resolve_from_email()
    if getattr(message, 'from_email', None) != resolved_from:
        original = getattr(message, 'from_email', '') or ''
        if original and original != resolved_from:
            logger.info('تصحيح From: %s → %s', original, resolved_from)
        message.from_email = resolved_from

    user = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip()
    reply_to = list(getattr(message, 'reply_to', None) or [])
    if user and user not in reply_to:
        message.reply_to = reply_to + [user]
    return message


def from_email_smtp_mismatch_warning() -> str:
    """تحذير إن كان مرسل الرسالة يختلف عن حساب SMTP (سبب شائع لعدم وصول البريد)."""
    user = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip().lower()
    from_addr = _extract_email_address(getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').lower()
    if user and from_addr and user != from_addr:
        return (
            f'DEFAULT_FROM_EMAIL ({from_addr}) يختلف عن EMAIL_HOST_USER ({user}) — '
            'بعض مزودي SMTP (مثل Hostinger) يرفضون الإرسال.'
        )
    return ''


def smtp_not_configured_message() -> str:
    return (
        'البريد غير مفعّل للإرسال الفعلي. '
        'اضبط EMAIL_HOST و EMAIL_HOST_USER و EMAIL_HOST_PASSWORD و DEFAULT_FROM_EMAIL '
        'في backend/.env (محلي) أو Environment في Dokploy (إنتاج) ثم أعد تشغيل السيرفر.'
    )


def ensure_smtp_ready(*, verify_connection: bool = False) -> None:
    """يرفع خطأ واضح إذا لم يكن SMTP جاهزاً."""
    if not is_real_smtp_delivery():
        raise SmtpNotConfiguredError(smtp_not_configured_message())

    mismatch = from_email_smtp_mismatch_warning()
    if mismatch:
        logger.warning(mismatch)

    if not verify_connection:
        return
    from django.core.mail import get_connection

    try:
        connection = get_connection()
        connection.open()
        connection.close()
    except Exception as exc:
        raise SmtpConnectionError(
            f'تعذّر الاتصال بـ SMTP ({settings.EMAIL_HOST}): {exc}'
        ) from exc


def deliver_email_message(message: Any, *, verify_connection: bool = True, log_context: str = '') -> int:
    """
    يتحقق من SMTP ثم يرسل الرسالة فعلياً.
    يرفع SmtpNotConfiguredError / SmtpConnectionError أو خطأ SMTP من Django.
    """
    ensure_smtp_ready(verify_connection=verify_connection)
    prepare_outbound_message(message)
    sent_count = message.send(fail_silently=False)
    recipients = list(getattr(message, 'to', None) or [])
    logger.info(
        'تم إرسال بريد (%s) من %s عبر %s إلى %s',
        log_context or 'outbound',
        message.from_email,
        email_delivery_mode(),
        ', '.join(recipients) or '-',
    )
    return sent_count
