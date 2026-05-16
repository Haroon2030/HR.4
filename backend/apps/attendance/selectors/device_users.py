"""استعلامات مستخدمي أجهزة البصمة — فلترة وبحث."""
from __future__ import annotations

from django.db.models import CharField, Exists, OuterRef, Q, QuerySet, Subquery

from apps.attendance.models import BiometricDeviceUser, EmployeeBiometricEnrollment

DEVICE_USER_LIST_ORDERING = ('device__name', 'device_user_id')
DEVICE_USERS_PER_PAGE = 10


def _active_enrollment_subquery():
    return EmployeeBiometricEnrollment.objects.filter(
        device_id=OuterRef('device_id'),
        device_user_id=OuterRef('device_user_id'),
        is_deleted=False,
    )


def get_device_user_queryset(
    *,
    device_id: int | None = None,
    branch_id: int | None = None,
    search: str | None = None,
    mapped_only: bool | None = None,
) -> QuerySet:
    enrollment = _active_enrollment_subquery()
    qs = (
        BiometricDeviceUser.objects.filter(is_deleted=False)
        .select_related('device', 'device__branch')
        .annotate(
            hr_employee_name=Subquery(
                enrollment.values('employee__name')[:1],
                output_field=CharField(),
            ),
            hr_employee_number=Subquery(
                enrollment.values('employee__employee_number')[:1],
                output_field=CharField(),
            ),
            is_hr_linked=Exists(enrollment),
        )
        .order_by(*DEVICE_USER_LIST_ORDERING)
    )

    if device_id:
        qs = qs.filter(device_id=device_id)
    if branch_id:
        qs = qs.filter(device__branch_id=branch_id)

    if mapped_only is True:
        qs = qs.filter(is_hr_linked=True)
    elif mapped_only is False:
        qs = qs.filter(is_hr_linked=False)

    if search:
        term = search.strip()
        if not term:
            return qs
        if term.isdigit():
            num = int(term)
            qs = qs.filter(
                Q(device_user_id=num)
                | Q(card__icontains=term)
                | Q(hr_employee_number__icontains=term)
            )
        else:
            name_match = enrollment.filter(employee__name__icontains=term)
            qs = qs.filter(
                Q(name__icontains=term)
                | Q(device__name__icontains=term)
                | Q(card__icontains=term)
                | Exists(name_match)
            )

    return qs
