"""استعلامات عمال الصيانة."""
from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.maintenance.models import MaintenanceWorker


def assignable_maintenance_workers_qs() -> QuerySet[MaintenanceWorker]:
    """عمال يمكن إسناد طلب لهم — نشطون، مهنتهم نشطة، ولديهم جوال."""
    return (
        MaintenanceWorker.objects.filter(
            is_active=True,
            trade__is_deleted=False,
            trade__is_active=True,
        )
        .filter(
            Q(phone__gt='') | Q(employee__phone__gt=''),
        )
        .select_related('trade', 'employee')
        .order_by('name', 'id')
    )
