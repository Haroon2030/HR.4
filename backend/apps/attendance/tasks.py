"""مهام Celery للحضور — تصدير كبير (اختياري مستقبلاً)."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1)
def reclassify_device_punches_task(self, device_id: int, requested_by_id: int | None = None) -> dict:
    """إعادة تصنيف بصمات جهاز بالتسلسل في الخلفية."""
    from apps.attendance.services.punch_inference import reclassify_punches_by_sequence

    result = reclassify_punches_by_sequence(device_id=device_id, dry_run=False)
    logger.info(
        'reclassify device=%s by=%s result=%s',
        device_id,
        requested_by_id,
        result,
    )
    return result
