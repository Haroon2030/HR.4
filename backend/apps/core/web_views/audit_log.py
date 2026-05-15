"""عرض موحّد لسجل التدقيق (Historical) للمدير العام ومدير الموارد."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.services.audit_feed import collect_audit_events
from apps.core.web_views._helpers import _user_accessible_branch_ids, general_manager_required


@login_required
@general_manager_required
def audit_history_dashboard(request):
    """جدول زمني مختصر لآخر التغييرات المسجّلة في simple_history."""
    source = (request.GET.get('source') or 'all').strip().lower()
    if source not in ('all', 'employee', 'pending_action', 'payroll_run', 'user_profile'):
        source = 'all'
    try:
        limit = int(request.GET.get('limit') or '60')
    except (TypeError, ValueError):
        limit = 60

    branch_ids = _user_accessible_branch_ids(request.user)
    if branch_ids is not None:
        branch_ids = set(branch_ids)

    events = collect_audit_events(branch_ids=branch_ids, source=source, limit=limit)

    return render(
        request,
        'pages/audit/history.html',
        {
            'events': events,
            'source': source,
            'limit': limit,
        },
    )
