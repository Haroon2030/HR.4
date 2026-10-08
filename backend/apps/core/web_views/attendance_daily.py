"""الحضور اليومي — شاشة مبسّطة: من حضر اليوم ومن عنده مشكلة تحتاج متابعة."""
from datetime import date, timedelta
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.attendance.selectors.daily_report import build_daily_attendance_rows
from apps.attendance.sub_permissions import ATTENDANCE_SCREEN_REPORT_VIEW
from apps.core.decorators import permission_required
from apps.core.models import Branch
from apps.core.web_views._helpers import _user_accessible_branch_ids
from apps.core.web_views.attendance_report import _punches_for_report

_ISSUE_LABELS = ('بصمة واحدة', 'غير مكتمل')
_STATUS_FILTERS = ('all', 'issues', 'unmapped', 'complete')
_PER_PAGE = 50


def _parse_date(raw: str | None) -> date:
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return timezone.localdate()


def _is_issue(row) -> bool:
    return row.status_label in _ISSUE_LABELS or not row.is_mapped


@permission_required(ATTENDANCE_SCREEN_REPORT_VIEW)
@require_GET
def attendance_daily(request):
    day = _parse_date(request.GET.get('date'))
    status = request.GET.get('status', 'all')
    if status not in _STATUS_FILTERS:
        status = 'all'
    search = (request.GET.get('q') or '').strip()

    branches_qs = Branch.objects.filter(is_deleted=False, is_active=True).order_by('name')
    accessible = _user_accessible_branch_ids(request.user)
    if accessible is not None:
        branches_qs = branches_qs.filter(pk__in=accessible)
    branch_raw = request.GET.get('branch', '')
    branch_id = int(branch_raw) if branch_raw.isdigit() else None
    if branch_id and not branches_qs.filter(pk=branch_id).exists():
        branch_id = None

    filters = {
        'branch_ids': [branch_id] if branch_id else [],
        'device_id': None,
        'employee_id': None,
        'device_user_id': None,
        'date_from': day.isoformat(),
        'date_to': day.isoformat(),
        'punch_type': None,
        'mapped_only': None,
        'search': search,
    }
    rows = build_daily_attendance_rows(_punches_for_report(request, filters))

    counts = {
        'present': len(rows),
        'complete': sum(1 for r in rows if r.status_label == 'مكتمل' and r.is_mapped),
        'issues': sum(1 for r in rows if _is_issue(r)),
        'unmapped': sum(1 for r in rows if not r.is_mapped),
    }

    if status == 'issues':
        rows = [r for r in rows if _is_issue(r)]
    elif status == 'unmapped':
        rows = [r for r in rows if not r.is_mapped]
    elif status == 'complete':
        rows = [r for r in rows if r.status_label == 'مكتمل' and r.is_mapped]
    # المشاكل أولاً ثم بقية الصفوف مرتبة بالاسم
    rows.sort(key=lambda r: (0 if _is_issue(r) else 1, r.employee_name or r.device_user_name or ''))

    page = Paginator(rows, per_page=_PER_PAGE).get_page(request.GET.get('page'))

    return render(request, 'pages/attendance/daily.html', {
        'day': day,
        'prev_day': day - timedelta(days=1),
        'next_day': day + timedelta(days=1),
        'is_today': day == timezone.localdate(),
        'today': timezone.localdate(),
        'status': status,
        'search': search,
        'branches': branches_qs,
        'branch_id': branch_id,
        'counts': counts,
        'page': page,
        'total_rows': len(rows),
        'qs': urlencode({k: v for k, v in request.GET.items() if k != 'page'}),
    })
