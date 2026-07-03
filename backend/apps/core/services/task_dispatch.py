"""تشغيل مهام Celery مع fallback متزامن في التطوير."""
from __future__ import annotations

from django.conf import settings


def celery_background_enabled() -> bool:
    """هل يُرسل العمل لعامل Celery بدلاً من تنفيذه في طلب HTTP؟"""
    broker = (getattr(settings, 'CELERY_BROKER_URL', None) or '').strip()
    if not broker:
        return False
    return not getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)


def dispatch_task(task, *args, **kwargs):
    """تشغيل مهمة — eager في التطوير، delay في الإنتاج."""
    if celery_background_enabled():
        return task.delay(*args, **kwargs)
    return task.apply(args=args, kwargs=kwargs)
