"""استعلامات سجلات الحضور — فلترة وإحصائيات."""
from __future__ import annotations

from datetime import date, datetime, time

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.attendance.models import AttendancePunch, BiometricDevice

# الأحدث أولاً: وقت البصمة ثم معرف السجل في قاعدة البيانات
PUNCH_LIST_ORDERING = ('-punched_at', '-id')


def get_punch_queryset(
    *,
    device_id: int | None = None,
    branch_id: int | None = None,
    employee_id: int | None = None,
    device_user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    punch_type: str | None = None,
    mapped_only: bool | None = None,
    search: str | None = None,
) -> QuerySet:
    qs = (
        AttendancePunch.objects.filter(is_deleted=False)
        .select_related('device', 'device__branch', 'employee')
        .order_by(*PUNCH_LIST_ORDERING)
    )
    if device_id:
        qs = qs.filter(device_id=device_id)
    if branch_id:
        qs = qs.filter(device__branch_id=branch_id)
    if employee_id:
        qs = qs.filter(employee_id=employee_id)
    if device_user_id:
        qs = qs.filter(device_user_id=device_user_id)
    if punch_type:
        qs = qs.filter(punch_type=punch_type)
    if mapped_only is True:
        qs = qs.filter(employee_id__isnull=False)
    elif mapped_only is False:
        qs = qs.filter(employee__isnull=True)
    if date_from:
        start = timezone.make_aware(datetime.combine(date_from, time.min))
        qs = qs.filter(punched_at__gte=start)
    if date_to:
        end = timezone.make_aware(datetime.combine(date_to, time.max))
        qs = qs.filter(punched_at__lte=end)
    if search:
        term = search.strip()
        if term.isdigit():
            qs = qs.filter(
                Q(device_user_id=int(term))
                | Q(employee__employee_number__icontains=term)
            )
        else:
            qs = qs.filter(
                Q(device_user_name__icontains=term)
                | Q(employee__name__icontains=term)
                | Q(device__name__icontains=term)
            )
    return qs


def get_punch_stats(qs: QuerySet | None = None, *, device_id: int | None = None) -> dict:
    from apps.attendance.services.punch_inference import device_status_health

    if qs is not None:
        stats_qs = qs._chain()
    else:
        stats_qs = AttendancePunch.objects.filter(is_deleted=False)
    agg = stats_qs.aggregate(
        total=Count('id'),
        check_in=Count('id', filter=Q(punch_type=AttendancePunch.PunchType.CHECK_IN)),
        check_out=Count('id', filter=Q(punch_type=AttendancePunch.PunchType.CHECK_OUT)),
        unmapped=Count('id', filter=Q(employee_id__isnull=True)),
        from_device=Count('id', filter=Q(punch_type_source=AttendancePunch.PunchTypeSource.DEVICE)),
        inferred=Count('id', filter=Q(punch_type_source=AttendancePunch.PunchTypeSource.INFERRED)),
    )
    status_health = device_status_health(device_id)
    first = stats_qs.order_by('punched_at').values_list('punched_at', flat=True).first()
    last = stats_qs.order_by('-punched_at').values_list('punched_at', flat=True).first()
    devices = BiometricDevice.objects.filter(is_deleted=False, is_active=True).count()
    return {
        **agg,
        'first_punch': first,
        'last_punch': last,
        'devices_count': devices,
        'status_health': status_health,
    }
