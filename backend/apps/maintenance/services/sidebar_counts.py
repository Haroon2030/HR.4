"""عداد طلبات الصيانة للشريط الجانبي."""
from __future__ import annotations

from apps.core.decorators import has_permission
from apps.maintenance.models import MaintenanceRequest
from apps.maintenance.services.access import filter_requests_for_user


def maintenance_open_requests_count(user) -> int:
    """طلبات غير مكتملة ضمن نطاق المستخدم (لشارة القائمة)."""
    if not user or not user.is_authenticated:
        return 0
    if not has_permission(user, 'maintenance.view'):
        return 0

    qs = filter_requests_for_user(
        user,
        MaintenanceRequest.objects.filter(is_deleted=False),
    )
    return qs.exclude(status=MaintenanceRequest.Status.BRANCH_CONFIRMED).count()


def invalidate_maintenance_sidebar_caches(request: MaintenanceRequest) -> None:
    """إبطال عدادات الشريط بعد تغيّر حالة طلب."""
    from apps.core.services.navigation_cache import invalidate_user_navigation_caches
    from apps.maintenance.services.recipients import branch_manager_for_request, maintenance_manager_users

    user_ids: set[int] = set()
    if request.requested_by_id:
        user_ids.add(request.requested_by_id)
    branch_manager = branch_manager_for_request(request)
    if branch_manager:
        user_ids.add(branch_manager.pk)
    for manager in maintenance_manager_users().only('pk'):
        user_ids.add(manager.pk)
    invalidate_user_navigation_caches(*user_ids)
