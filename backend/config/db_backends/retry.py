"""إعادة محاولة فتح اتصال قاعدة البيانات عند ازدحام الخادم المشترك (MySQL 1040)."""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# 1040 = Too many connections: امتلأ حدّ اتصالات الخادم المشترك لحظياً — إعادة محاولة قصيرة تكفي غالباً.
TOO_MANY_CONNECTIONS = 1040
CONNECT_RETRY_DELAYS = (0.3, 0.8, 1.5)


def is_too_many_connections(exc: BaseException) -> bool:
    return bool(getattr(exc, 'args', None)) and exc.args[0] == TOO_MANY_CONNECTIONS


def connect_with_retry(connect, error_cls, *, delays=CONNECT_RETRY_DELAYS, sleep=time.sleep):
    """ينفّذ connect() ويعيد المحاولة عند 1040 فقط؛ أي خطأ آخر يُرفع فوراً."""
    for attempt, delay in enumerate((*delays, None), start=1):
        try:
            return connect()
        except error_cls as exc:
            if delay is None or not is_too_many_connections(exc):
                raise
            logger.warning('MySQL: too many connections — إعادة المحاولة %s بعد %.1fث', attempt, delay)
            sleep(delay)
