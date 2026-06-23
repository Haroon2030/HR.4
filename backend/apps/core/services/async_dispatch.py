"""تشغيل مهام خفيفة في الخلفية دون حجب استجابة HTTP."""
from __future__ import annotations

import logging
import threading
from typing import Callable

from django.conf import settings

logger = logging.getLogger(__name__)


def dispatch_background(task_name: str, fn: Callable[[], None]) -> None:
    """تنفيذ fn في خيط منفصل عند تفعيل WHATSAPP_ASYNC_DISPATCH."""
    if not getattr(settings, 'WHATSAPP_ASYNC_DISPATCH', False):
        _run_safe(task_name, fn)
        return

    thread = threading.Thread(
        target=_run_safe,
        args=(task_name, fn),
        daemon=True,
        name=f'hr-bg-{task_name}',
    )
    thread.start()


def _run_safe(task_name: str, fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception as exc:
        logger.warning('background task %s failed: %s', task_name, exc)
