"""رسائل خطأ آمنة للمستخدم — بدون كشف تفاصيل داخلية."""
from __future__ import annotations

import logging

from apps.core.services.email_delivery import SmtpConnectionError, SmtpNotConfiguredError

logger = logging.getLogger(__name__)

GENERIC_ACTION_ERROR = 'تعذّر إتمام العملية. يرجى المحاولة لاحقاً أو التواصل مع الدعم.'
GENERIC_LEDGER_ERROR = 'تعذّر تهيئة الرصيد. يرجى المحاولة لاحقاً أو التواصل مع الدعم.'
GENERIC_EMAIL_PARTIAL = 'تم الحفظ لكن فشل الإرسال بالبريد. تحقق من إعدادات SMTP أو تواصل مع الدعم.'


def log_web_action_error(
    context: str,
    exc: BaseException,
    *,
    user_message: str | None = None,
) -> str:
    logger.exception('%s failed', context, exc_info=exc)
    return user_message or GENERIC_ACTION_ERROR


def log_email_partial_failure(context: str, exc: BaseException) -> str:
    logger.exception('%s email failed', context, exc_info=exc)
    if isinstance(exc, (SmtpNotConfiguredError, SmtpConnectionError)):
        return str(exc) or GENERIC_EMAIL_PARTIAL
    return GENERIC_EMAIL_PARTIAL
