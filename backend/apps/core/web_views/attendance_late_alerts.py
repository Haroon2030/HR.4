"""صفحة إنذارات تأخير البصمة."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.attendance.selectors.biometric_devices import get_biometric_devices_queryset
from apps.attendance.selectors.late_alerts import build_late_checkin_alerts, summarize_late_alerts
from apps.core.decorators import permission_required
from apps.core.models import Branch
from apps.core.utils.attendance_filters import clamp_attendance_date_range
from apps.core.web_views._helpers import _user_accessible_branch_ids
from apps.core.web_views.attendance_records import (
    _apply_default_date_filters,
    _filters_to_querystring,
    _parse_filters,
)
from apps.employees.models import Employee


@permission_required('attendance.view')
@require_GET
def attendance_late_alerts(request):
    filters = _apply_default_date_filters(_parse_filters(request))
    filters, date_clamped = clamp_attendance_date_range(filters)
    if date_clamped:
        messages.warning(
            request,
            'تم تقييد الفترة إلى 93 يوماً كحد أقصى لاستعلامات البصمة.',
        )

    alerts = build_late_checkin_alerts(request.user, filters)
    summary = summarize_late_alerts(alerts)

    paginator = Paginator(alerts, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    filter_employee = None
    if filters.get('employee_id'):
        filter_employee = Employee.objects.filter(pk=filters['employee_id']).first()

    branch_ids = _user_accessible_branch_ids(request.user)
    branches = Branch.objects.filter(pk__in=branch_ids).order_by('name') if branch_ids else Branch.objects.none()

    querystring = _filters_to_querystring(filters)
    mapped_filter = 'yes' if filters.get('mapped_only') is True else (
        'no' if filters.get('mapped_only') is False else 'all'
    )

    return render(request, 'pages/attendance/late_alerts.html', {
        'page_obj': page_obj,
        'alerts': page_obj.object_list,
        'summary': summary,
        'filters': filters,
        'querystring': querystring,
        'branches': branches,
        'devices': get_biometric_devices_queryset(request.user),
        'filter_employee': filter_employee,
        'mapped_filter': mapped_filter,
        'employee_search_url': request.build_absolute_uri('/employees/search/'),
    })
