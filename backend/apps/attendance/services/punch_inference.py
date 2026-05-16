"""
استنتاج دخول/خروج من تسلسل البصمات عندما لا يرسل الجهاز status صحيحاً.

شائع في uFace وبعض إصدارات ZKTeco: كل السجلات تأتي بـ status=1 بينما
الحقل punch يعني طريقة التحقق (بصمة/وجه) وليس اتجاه الحركة.
"""
from __future__ import annotations

from collections import defaultdict
from django.db import transaction
from django.utils import timezone

from apps.attendance.models import AttendancePunch


def device_status_health(device_id: int | None = None) -> dict:
    """تحليل جودة حقل status من الجهاز."""
    qs = AttendancePunch.objects.filter(is_deleted=False)
    if device_id:
        qs = qs.filter(device_id=device_id)
    total = qs.count()
    if not total:
        return {'total': 0, 'status_0': 0, 'status_1': 0, 'status_other': 0, 'skewed': False}

    status_0 = qs.filter(raw_status=0).count()
    status_1 = qs.filter(raw_status=1).count()
    status_other = total - status_0 - status_1
    # إذا أكثر من 85% من سجل واحد → الجهاز لا يميّز دخول/خروج
    dominant = max(status_0, status_1)
    skewed = total > 20 and (dominant / total) >= 0.85
    return {
        'total': total,
        'status_0': status_0,
        'status_1': status_1,
        'status_other': status_other,
        'skewed': skewed,
        'dominant_status': 0 if status_0 >= status_1 else 1,
    }


def infer_punch_type_for_sequence(index: int) -> str:
    """أول بصمة في اليوم = دخول، الثانية خروج، وهكذا."""
    return AttendancePunch.PunchType.CHECK_IN if index % 2 == 0 else AttendancePunch.PunchType.CHECK_OUT


def reclassify_punches_by_sequence(
    *,
    device_id: int | None = None,
    dry_run: bool = False,
) -> dict:
    """
    إعادة تصنيف punch_type حسب ترتيب الوقت لكل (جهاز، مستخدم، يوم).
    """
    qs = AttendancePunch.objects.filter(is_deleted=False).order_by('punched_at')
    if device_id:
        qs = qs.filter(device_id=device_id)

    groups: dict[tuple, list[AttendancePunch]] = defaultdict(list)
    for punch in qs.iterator(chunk_size=2000):
        day = timezone.localtime(punch.punched_at).date()
        key = (punch.device_id, punch.device_user_id, day)
        groups[key].append(punch)

    updated = 0
    in_count = 0
    out_count = 0
    to_update: list[AttendancePunch] = []

    for punches in groups.values():
        punches.sort(key=lambda p: p.punched_at)
        for i, punch in enumerate(punches):
            new_type = infer_punch_type_for_sequence(i)
            if new_type == AttendancePunch.PunchType.CHECK_IN:
                in_count += 1
            else:
                out_count += 1
            if punch.punch_type != new_type or punch.punch_type_source != AttendancePunch.PunchTypeSource.INFERRED:
                punch.punch_type = new_type
                punch.punch_type_source = AttendancePunch.PunchTypeSource.INFERRED
                to_update.append(punch)
                updated += 1

    if not dry_run and to_update:
        with transaction.atomic():
            AttendancePunch.objects.bulk_update(
                to_update,
                ['punch_type', 'punch_type_source'],
                batch_size=500,
            )

    return {
        'updated': updated,
        'inferred_in': in_count,
        'inferred_out': out_count,
        'total': in_count + out_count,
        'dry_run': dry_run,
    }
