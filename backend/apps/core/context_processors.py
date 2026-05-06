"""Template context processors."""
import logging
from django.db.models import Q

logger = logging.getLogger(__name__)


def _pending_statuses():
    from apps.core.models import PendingAction
    return [
        PendingAction.Status.PENDING_BRANCH,
        PendingAction.Status.PENDING_GM,
        PendingAction.Status.PENDING_OFFICER,
    ]


def pending_actions_count(request):
    """إجمالي الطلبات المعلّقة الظاهرة لهذا المستخدم (لشارة القائمة الجانبية)."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    try:
        from apps.core.models import PendingAction
        qs = PendingAction.objects.filter(status__in=_pending_statuses())
        if user.is_superuser:
            count = qs.count()
        else:
            managed_ids = list(user.managed_branches.values_list('id', flat=True))
            f = Q(requested_by=user) | Q(assigned_officer=user)
            if managed_ids:
                f |= Q(branch_id__in=managed_ids)
            count = qs.filter(f).distinct().count()
        return {'pending_actions_count': count}
    except Exception as e:
        logger.warning("pending_actions_count context failed: %s", e)
        return {'pending_actions_count': 0}


def approval_inbox(request):
    """عدد الطلبات التي تنتظر إجراءً من المستخدم الحالي + عدد الإشعارات غير المقروءة."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    try:
        from apps.core.models import PendingAction, Notification
        from apps.core.web_views._helpers import (
            _is_branch_manager, _is_general_manager, _is_hr_officer,
        )

        f = Q()
        if user.is_superuser or _is_general_manager(user):
            f |= Q(status=PendingAction.Status.PENDING_GM)
        if _is_branch_manager(user):
            managed_ids = list(user.managed_branches.values_list('id', flat=True))
            if managed_ids:
                f |= Q(status=PendingAction.Status.PENDING_BRANCH, branch_id__in=managed_ids)
        if _is_hr_officer(user):
            f |= Q(status=PendingAction.Status.PENDING_OFFICER, assigned_officer=user)
        f |= Q(status=PendingAction.Status.RETURNED, requested_by=user)

        pending_for_me_count = PendingAction.objects.filter(f).distinct().count()
        unread = Notification.objects.filter(recipient=user, is_read=False).count()
        return {
            'pending_for_me_count': pending_for_me_count,
            'unread_notifications_count': unread,
        }
    except Exception as e:
        logger.warning("approval_inbox context failed: %s", e)
        return {
            'pending_for_me_count': 0,
            'unread_notifications_count': 0,
        }
