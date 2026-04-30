"""Template context processors."""
from django.db.models import Q


def pending_actions_count(request):
    """عدد طلبات العمليات المعلّقة الظاهرة لهذا المستخدم."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    try:
        from apps.core.models import PendingAction
        qs = PendingAction.objects.filter(status='pending')
        if user.is_superuser:
            count = qs.count()
        else:
            managed_ids = list(user.managed_branches.values_list('id', flat=True))
            if managed_ids:
                count = qs.filter(Q(branch_id__in=managed_ids) | Q(requested_by=user)).count()
            else:
                count = qs.filter(requested_by=user).count()
        return {'pending_actions_count': count}
    except Exception:
        return {'pending_actions_count': 0}
