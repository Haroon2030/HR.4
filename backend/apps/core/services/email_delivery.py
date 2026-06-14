"""حالة إرسال البريد الفعلي (SMTP مقابل وضع التطوير)."""
from __future__ import annotations

from django.conf import settings


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
