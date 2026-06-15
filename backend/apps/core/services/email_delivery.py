"""حالة إرسال البريد الفعلي (SMTP مقابل وضع التطوير)."""
from __future__ import annotations

from django.conf import settings


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
    return {
        'mode': mode,
        'smtp_ready': smtp_ready,
        'backend': getattr(settings, 'EMAIL_BACKEND', ''),
        'host': (getattr(settings, 'EMAIL_HOST', '') or '').strip(),
        'from_email': (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip(),
    }


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
