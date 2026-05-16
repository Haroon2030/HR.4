"""استعلامات أجهزة البصمة — عزل حسب الفرع وصلاحيات المستخدم."""
from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.attendance.models import BiometricDevice
from apps.core.web_views._helpers import _user_accessible_branch_ids


def filter_biometric_devices_for_user(user, queryset: QuerySet | None = None) -> QuerySet:
    qs = queryset if queryset is not None else BiometricDevice.objects.filter(is_deleted=False)
    branch_ids = _user_accessible_branch_ids(user)
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=branch_ids)
    return qs


def get_biometric_devices_queryset(
    user,
    *,
    branch_id: int | None = None,
    active_only: bool = False,
) -> QuerySet:
    qs = (
        filter_biometric_devices_for_user(user)
        .select_related('branch')
        .annotate(
            punch_count=Count('punches', filter=Q(punches__is_deleted=False)),
        )
        .order_by('branch__name', 'name')
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs


def get_device_for_user(user, device_id: int) -> BiometricDevice:
    from django.shortcuts import get_object_or_404

    return get_object_or_404(
        filter_biometric_devices_for_user(user),
        pk=device_id,
        is_deleted=False,
    )


def make_sync_batch_label(device: BiometricDevice) -> str:
    """دفعة مزامنة فريدة لكل جهاز/فرع — لتتبع السحب دون خلط الفروع."""
    import uuid

    branch_part = device.branch_id or 0
    return f'd{device.pk}-b{branch_part}-{uuid.uuid4().hex[:8]}'
