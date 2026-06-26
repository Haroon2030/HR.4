"""سجلات الحضور — عرض تقني مع فلترة وتصفح وتصدير."""
from datetime import datetime, time

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.attendance.models import AttendancePunch, BiometricDevice
from apps.attendance.selectors.punch_records import (
    PUNCH_LIST_ORDERING,
    get_punch_queryset,
    get_punch_stats,
)
from apps.attendance.services.agent_pull_queue import queue_lan_device_sync
from apps.attendance.services.attendance_pull import pull_device_attendance
from apps.attendance.services.punch_inference import reclassify_punches_by_sequence
from apps.attendance.selectors.biometric_devices import (
    filter_biometric_devices_for_user,
    get_biometric_devices_queryset,
)
from apps.core.decorators import permission_required
from apps.core.filter_utils import append_multi_param, parse_multi_filter_ids
from apps.core.models import Branch
from apps.core.web_views._helpers import _user_accessible_branch_ids

_VALID_PUNCH_TYPES = frozenset(AttendancePunch.PunchType.values)


def _apply_default_date_filters(filters: dict) -> dict:
    """يُستخدم في تقرير البصمة فقط — فرض من/إلى افتراضيين عند غيابهما في الاستعلام."""
    if not filters.get('date_from') and not filters.get('date_to'):
        today = timezone.localdate()
        filters = {
            **filters,
            'date_from': today.replace(day=1).isoformat(),
            'date_to': today.isoformat(),
        }
    return filters


def _parse_filters(request) -> dict:
    accessible = _user_accessible_branch_ids(request.user)
    branch_ids = parse_multi_filter_ids(request, 'branch', accessible_ids=accessible)
    device_id = request.GET.get('device') or None
    employee_id = request.GET.get('employee') or None
    device_user_id = request.GET.get('device_user') or None
    date_from = request.GET.get('from') or None
    date_to = request.GET.get('to') or None
    raw_punch_type = (request.GET.get('punch_type') or '').strip()
    punch_type = raw_punch_type if raw_punch_type in _VALID_PUNCH_TYPES else None
    mapped = request.GET.get('mapped')
    mapped_only = None
    if mapped == '1':
        mapped_only = True
    elif mapped == '0':
        mapped_only = False
    return {
        'branch_ids': branch_ids,
        'device_id': int(device_id) if device_id and device_id.isdigit() else None,
        'employee_id': int(employee_id) if employee_id and employee_id.isdigit() else None,
        'device_user_id': int(device_user_id) if device_user_id and device_user_id.isdigit() else None,
        'date_from': date_from,
        'date_to': date_to,
        'punch_type': punch_type,
        'mapped_only': mapped_only,
        'search': (request.GET.get('q') or '').strip(),
    }


def _filters_to_querystring(filters: dict, *, extra: dict | None = None) -> str:
    from urllib.parse import urlencode

    params: list[tuple[str, object]] = []
    append_multi_param(params, 'branch', filters.get('branch_ids'))
    if filters.get('device_id'):
        params.append(('device', filters['device_id']))
    if filters.get('employee_id'):
        params.append(('employee', filters['employee_id']))
    if filters.get('device_user_id'):
        params.append(('device_user', filters['device_user_id']))
    if filters.get('date_from'):
        params.append(('from', filters['date_from']))
    if filters.get('date_to'):
        params.append(('to', filters['date_to']))
    if filters.get('punch_type'):
        params.append(('punch_type', filters['punch_type']))
    if filters.get('mapped_only') is True:
        params.append(('mapped', '1'))
    elif filters.get('mapped_only') is False:
        params.append(('mapped', '0'))
    if filters.get('search'):
        params.append(('q', filters['search']))
    if extra:
        for k, v in extra.items():
            if v is not None and v != '':
                params.append((k, v))
    return urlencode(params, doseq=True)


@permission_required('attendance.view')
def attendance_records_list(request):
    filters = _parse_filters(request)
    filter_employee = None
    employee_enrollments = []

    if filters['employee_id']:
        from apps.attendance.selectors.employee_enrollment import apply_employee_enrollment_to_filters
        from apps.employees.models import Employee

        filter_employee = get_object_or_404(
            Employee.objects.select_related('branch', 'department'),
            pk=filters['employee_id'],
        )
        filters = apply_employee_enrollment_to_filters(filters, filter_employee.id)
        employee_enrollments = filters.get('enrollments') or []

    date_from = None
    date_to = None
    if filters['date_from']:
        date_from = datetime.strptime(filters['date_from'], '%Y-%m-%d').date()
    if filters['date_to']:
        date_to = datetime.strptime(filters['date_to'], '%Y-%m-%d').date()

    qs = get_punch_queryset(
        device_id=filters['device_id'],
        branch_ids=filters['branch_ids'],
        employee_id=None,
        device_user_id=filters['device_user_id'],
        date_from=date_from,
        date_to=date_to,
        punch_type=filters['punch_type'],
        mapped_only=filters['mapped_only'],
        search=filters['search'] or None,
    ).filter(device_id__in=filter_biometric_devices_for_user(request.user).values('pk'))

    if employee_enrollments:
        from apps.attendance.selectors.employee_enrollment import enrollment_filter_q
        qs = qs.filter(enrollment_filter_q(employee_enrollments))
    elif filters['employee_id']:
        qs = qs.filter(employee_id=filters['employee_id'])
    stats = get_punch_stats(qs, device_id=filters['device_id'])
    qs = qs.order_by(*PUNCH_LIST_ORDERING)
    from apps.core.utils.pagination import clamp_page_size

    paginator = Paginator(
        qs,
        per_page=clamp_page_size(request.GET.get('per_page'), default=100, maximum=200),
    )
    page_obj = paginator.get_page(request.GET.get('page'))

    devices = get_biometric_devices_queryset(request.user)
    branches_qs = Branch.objects.filter(is_deleted=False, is_active=True).order_by('name')
    accessible = _user_accessible_branch_ids(request.user)
    if accessible is not None:
        branches_qs = branches_qs.filter(pk__in=accessible)

    from apps.attendance.selectors.employee_enrollment import preferred_device_id

    sync_device_id = filters.get('device_id') or preferred_device_id(employee_enrollments)

    return render(request, 'pages/attendance/records.html', {
        'branches': branches_qs,
        'page_obj': page_obj,
        'stats': stats,
        'devices': devices,
        'filters': filters,
        'employee_search_url': reverse('web:employee_picker_search'),
        'filter_employee': filter_employee,
        'employee_enrollments': employee_enrollments,
        'sync_device_id': sync_device_id,
        'querystring': _filters_to_querystring(filters),
        'qs_punch_all': _filters_to_querystring({**filters, 'punch_type': None}),
        'qs_punch_in': _filters_to_querystring({**filters, 'punch_type': 'in'}),
        'qs_punch_out': _filters_to_querystring({**filters, 'punch_type': 'out'}),
        'per_page': paginator.per_page,
    })


def _attendance_pull_wants_json(request) -> bool:
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@permission_required('attendance.manage')
@require_POST
def attendance_records_pull(request):
    wants_json = _attendance_pull_wants_json(request)

    def _json_err(msg: str, status: int = 400):
        if wants_json:
            return JsonResponse({'ok': False, 'error': msg}, status=status)
        messages.error(request, msg)
        return redirect('web:attendance_records')

    device_id = request.POST.get('device_id')
    if not device_id:
        return _json_err('اختر جهازاً للسحب.')

    from apps.attendance.selectors.biometric_devices import get_device_for_user

    device = get_device_for_user(request.user, int(device_id))
    if not device.branch_id:
        return _json_err(f'حدّد فرعاً لجهاز «{device.name}» قبل السحب.')
    date_from = request.POST.get('date_from') or None
    date_to = request.POST.get('date_to') or None
    df = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
    dt = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None

    queued, queue_msg = queue_lan_device_sync(
        device,
        date_from=df,
        date_to=dt,
        requested_by_id=request.user.pk,
    )
    if queued:
        full_msg = queue_msg + ' حدّث الصفحة بعد قليل.'
        if wants_json:
            return JsonResponse({
                'ok': True,
                'queued': True,
                'message': full_msg,
            })
        messages.success(request, full_msg)
        return redirect('web:attendance_records')

    result = pull_device_attendance(
        device,
        date_from=df,
        date_to=dt,
        import_db=True,
        force_mock=False,
    )
    if result.ok:
        msg = (
            f'«{device.name}»: على الجهاز {result.punches_fetched} — '
            f'جديد {result.punches_new} — مستورد {result.imported} — '
            f'مكرر {result.skipped_duplicate}'
        )
        if result.skipped_time_filter:
            msg += f' — قديم {result.skipped_time_filter}'
        if wants_json:
            return JsonResponse({
                'ok': True,
                'queued': False,
                'message': msg,
                'punches_fetched': result.punches_fetched,
                'punches_new': result.punches_new,
                'imported': result.imported,
                'skipped_duplicate': result.skipped_duplicate,
                'skipped_time_filter': result.skipped_time_filter,
            })
        messages.success(request, msg)
    else:
        if wants_json:
            return JsonResponse({'ok': False, 'error': result.error or 'فشل السحب'})
        messages.error(request, result.error)
    return redirect('web:attendance_records')


@permission_required('attendance.manage')
@require_POST
def attendance_records_reclassify(request):
    device_id = request.POST.get('device_id')
    did = int(device_id) if device_id and str(device_id).isdigit() else None
    result = reclassify_punches_by_sequence(device_id=did, dry_run=False)
    messages.success(
        request,
        f'تم إعادة التصنيف بالتسلسل: دخول {result["inferred_in"]} · خروج {result["inferred_out"]} '
        f'(حدّث {result["updated"]} سجل)',
    )
    url = reverse('web:attendance_records')
    if did:
        url = f'{url}?device={did}'
    return redirect(url)


@permission_required('attendance.view')
@require_GET
def attendance_records_export(request):
    filters = _parse_filters(request)
    date_from = datetime.strptime(filters['date_from'], '%Y-%m-%d').date() if filters.get('date_from') else None
    date_to = datetime.strptime(filters['date_to'], '%Y-%m-%d').date() if filters.get('date_to') else None

    qs = get_punch_queryset(
        device_id=filters['device_id'],
        branch_ids=filters['branch_ids'],
        employee_id=filters['employee_id'],
        device_user_id=filters['device_user_id'],
        date_from=date_from,
        date_to=date_to,
        punch_type=filters['punch_type'],
        mapped_only=filters['mapped_only'],
        search=filters['search'] or None,
    ).filter(
        device_id__in=filter_biometric_devices_for_user(request.user).values('pk'),
    ).order_by(*PUNCH_LIST_ORDERING)[:50000]

    from apps.attendance.selectors.punch_export import (
        punches_to_table_rows,
        punch_table_http_response,
    )

    table = punches_to_table_rows(qs)
    return punch_table_http_response(table, filename_prefix='attendance_records')
