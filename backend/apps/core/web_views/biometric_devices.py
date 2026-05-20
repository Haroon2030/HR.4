"""واجهة إدارة أجهزة البصمة."""
from django.contrib import messages
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.attendance.models import (
    AttendancePunch,
    BiometricDevice,
    BiometricDeviceUser,
    EmployeeBiometricEnrollment,
)
from apps.attendance.selectors.biometric_devices import (
    filter_biometric_devices_for_user,
    get_biometric_devices_queryset,
    get_device_for_user,
)
from apps.attendance.selectors.device_users import DEVICE_USERS_PER_PAGE, get_device_user_queryset
from apps.attendance.services.branch_setup import ensure_branch_for_device
from apps.attendance.services.device_primary_key import (
    create_biometric_device_with_id,
    parse_requested_device_id,
    reassign_biometric_device_id,
)
from apps.attendance.services.device_purge import purge_biometric_device
from apps.attendance.validators import validate_device_ipv4
from apps.attendance.services.agent_pull_queue import queue_lan_device_sync
from apps.attendance.services.zk_client import (
    probe_device,
    sync_device_attendance,
    sync_device_users,
)
from apps.attendance.validators import cloud_pull_blocked_message
from apps.core.decorators import permission_required
from apps.core.models import Branch
from apps.core.web_views._helpers import _user_accessible_branch_ids, filter_employees_queryset_for_user
from apps.employees.models import Employee


def _parse_branch_filter(request) -> int | None:
    branch_id = request.GET.get('branch')
    return int(branch_id) if branch_id and branch_id.isdigit() else None


def _accessible_branches(user):
    qs = Branch.objects.filter(is_deleted=False, is_active=True).order_by('name')
    branch_ids = _user_accessible_branch_ids(user)
    if branch_ids is not None:
        qs = qs.filter(pk__in=branch_ids)
    return qs


def _parse_device_user_filters(request) -> dict:
    device_id = request.GET.get('users_device') or None
    mapped = request.GET.get('users_mapped')
    mapped_only = None
    if mapped == '1':
        mapped_only = True
    elif mapped == '0':
        mapped_only = False
    return {
        'branch_id': _parse_branch_filter(request),
        'device_id': int(device_id) if device_id and device_id.isdigit() else None,
        'search': (request.GET.get('users_q') or '').strip(),
        'mapped_only': mapped_only,
    }


def _device_users_querystring(filters: dict, *, extra: dict | None = None) -> str:
    from urllib.parse import urlencode

    params = {}
    if filters.get('branch_id'):
        params['branch'] = filters['branch_id']
    if filters.get('device_id'):
        params['users_device'] = filters['device_id']
    if filters.get('search'):
        params['users_q'] = filters['search']
    if filters.get('mapped_only') is True:
        params['users_mapped'] = '1'
    elif filters.get('mapped_only') is False:
        params['users_mapped'] = '0'
    if extra:
        params.update(extra)
    return urlencode(params)


@permission_required('attendance.view')
def biometric_devices_dashboard(request):
    branch_filter_id = _parse_branch_filter(request)
    devices = get_biometric_devices_queryset(request.user, branch_id=branch_filter_id)
    branches = _accessible_branches(request.user)

    enrollments_qs = (
        EmployeeBiometricEnrollment.objects.filter(is_deleted=False)
        .select_related('employee', 'device', 'device__branch')
        .order_by('device__branch__name', 'device__name', 'device_user_id')
    )
    if branch_filter_id:
        enrollments_qs = enrollments_qs.filter(device__branch_id=branch_filter_id)
    enrollments = list(enrollments_qs[:100])

    enrollment_by_device_user_qs = (
        EmployeeBiometricEnrollment.objects.filter(is_deleted=False)
        .select_related('employee', 'device')
    )
    if branch_filter_id:
        enrollment_by_device_user_qs = enrollment_by_device_user_qs.filter(
            device__branch_id=branch_filter_id,
        )
    enrollment_by_device_user = {
        (e.device_id, e.device_user_id): e
        for e in enrollment_by_device_user_qs
    }

    device_user_filters = _parse_device_user_filters(request)
    device_users_qs = get_device_user_queryset(
        device_id=device_user_filters['device_id'],
        branch_id=device_user_filters['branch_id'],
        search=device_user_filters['search'] or None,
        mapped_only=device_user_filters['mapped_only'],
    )
    device_users_paginator = Paginator(device_users_qs, per_page=DEVICE_USERS_PER_PAGE)
    device_users_page = device_users_paginator.get_page(request.GET.get('users_page'))
    device_users_stats = device_users_qs.aggregate(
        total=Count('pk'),
        unmapped=Count('pk', filter=Q(is_hr_linked=False)),
    )
    device_users_has_filters = any([
        device_user_filters['branch_id'],
        device_user_filters['device_id'],
        device_user_filters['search'],
        device_user_filters['mapped_only'] is not None,
    ])
    employees = filter_employees_queryset_for_user(
        request.user,
        Employee.objects.filter(is_deleted=False, status=Employee.Status.ACTIVE)
        .select_related('branch', 'department')
        .order_by('name'),
    )

    link_device_id = request.GET.get('link_device')
    link_user_id = request.GET.get('link_user')
    link_device_user = None
    if link_device_id and link_user_id and str(link_user_id).isdigit():
        link_device_user = BiometricDeviceUser.objects.filter(
            device_id=int(link_device_id),
            device_user_id=int(link_user_id),
            is_deleted=False,
        ).select_related('device').first()

    devices_without_branch = filter_biometric_devices_for_user(
        request.user,
        BiometricDevice.objects.filter(is_deleted=False, branch__isnull=True),
    ).count()

    return render(request, 'pages/attendance/biometric_devices.html', {
        'devices': devices,
        'branch_filter_id': branch_filter_id,
        'devices_without_branch': devices_without_branch,
        'enrollments': enrollments,
        'device_users_page': device_users_page,
        'device_users_total': device_users_paginator.count,
        'device_users_stats': device_users_stats,
        'device_user_filters': device_user_filters,
        'device_users_has_filters': device_users_has_filters,
        'users_querystring': _device_users_querystring(device_user_filters),
        'device_users_per_page': DEVICE_USERS_PER_PAGE,
        'enrollment_by_device_user': enrollment_by_device_user,
        'branches': branches,
        'employees': employees,
        'link_device_id': link_device_id,
        'link_user_id': link_user_id,
        'link_device_user': link_device_user,
        'employees_count': employees.count(),
    })


@permission_required('attendance.manage')
@require_POST
def biometric_device_save(request):
    original_device_id_raw = (request.POST.get('original_device_id') or '').strip()
    requested_device_id_raw = (request.POST.get('device_id') or '').strip()
    name = (request.POST.get('name') or '').strip()
    ip_address = (request.POST.get('ip_address') or '').strip()
    port = int(request.POST.get('port') or 4370)
    comm_key = int(request.POST.get('comm_key') or 0)
    branch_id_raw = (request.POST.get('branch_id') or '').strip()
    is_active = request.POST.get('is_active') == 'on'

    if not name:
        messages.error(request, 'اسم الجهاز مطلوب.')
        return redirect('web:biometric_devices')

    try:
        ip_address = validate_device_ipv4(ip_address)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('web:biometric_devices')

    if port < 1 or port > 65535:
        messages.error(request, 'المنفذ يجب أن يكون بين 1 و 65535.')
        return redirect('web:biometric_devices')

    if not branch_id_raw:
        messages.error(request, 'اختر الفرع من القائمة.')
        return redirect('web:biometric_devices')

    try:
        requested_device_id = parse_requested_device_id(requested_device_id_raw)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('web:biometric_devices')

    is_update = bool(original_device_id_raw and original_device_id_raw.isdigit())
    if is_update:
        device = get_device_for_user(request.user, int(original_device_id_raw))
    else:
        device = BiometricDevice()

    try:
        branch_id = int(branch_id_raw) if branch_id_raw else None
        if branch_id and not _accessible_branches(request.user).filter(pk=branch_id).exists():
            messages.error(request, 'الفرع غير متاح لحسابك.')
            return redirect('web:biometric_devices')
        branch = ensure_branch_for_device(
            branch_id=branch_id,
            branch_name=None,
            device_name=None,
        )
    except Branch.DoesNotExist:
        messages.error(request, 'الفرع المحدد غير موجود.')
        return redirect('web:biometric_devices')
    except ValueError:
        messages.error(request, 'حدّد الفرع لإتمام الربط بالموظفين.')
        return redirect('web:biometric_devices')

    device.name = name
    device.ip_address = ip_address
    device.port = port
    device.comm_key = comm_key
    device.branch_id = branch.id
    device.is_active = is_active

    try:
        if is_update:
            if requested_device_id is not None and requested_device_id != device.pk:
                device = reassign_biometric_device_id(device, requested_device_id)
            device.save()
        elif requested_device_id is not None:
            create_biometric_device_with_id(device, requested_device_id)
        else:
            device.save()
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('web:biometric_devices')

    messages.success(
        request,
        f'تم حفظ الجهاز «{device.name}» (رقم {device.pk}) وربطه بفرع «{branch.name}» — يمكنك الآن ربط الموظفين بالأسفل.',
    )
    from django.urls import reverse
    return redirect('web:biometric_devices')


@permission_required('attendance.manage')
@require_POST
def biometric_device_delete(request, device_id):
    device = get_device_for_user(request.user, device_id)
    name = device.name
    pk = device.pk
    counts = purge_biometric_device(device)
    messages.success(
        request,
        f'تم حذف الجهاز «{name}» (رقم {pk}) نهائياً من قاعدة البيانات — '
        f'{counts["punches"]} بصمة، {counts["device_users"]} مستخدم جهاز، '
        f'{counts["enrollments"]} ربط موظف. يمكنك إعادة استخدام الرقم {pk}.',
    )
    return redirect('web:biometric_devices')


@permission_required('attendance.manage')
@require_POST
def biometric_device_test(request, device_id):
    device = get_device_for_user(request.user, device_id)
    lan_msg = cloud_pull_blocked_message(device, force_mock=False)
    if lan_msg:
        result_payload = {
            'ok': False,
            'message': (
                'اختبار الاتصال من السحابة غير متاح لعناوين LAN. '
                'من PC الفرع: python agent.py --probe'
            ),
        }
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse(result_payload)
        messages.warning(request, result_payload['message'])
        return redirect('web:biometric_devices')

    result = probe_device(device, force_mock=False)

    if result.ok:
        device.connection_status = BiometricDevice.ConnectionStatus.ONLINE
        if result.serial_number:
            device.serial_number = result.serial_number
        if result.firmware:
            device.firmware_version = result.firmware
        device.last_error = ''
    else:
        device.connection_status = BiometricDevice.ConnectionStatus.ERROR
        device.last_error = result.message

    from django.utils import timezone
    device.last_ping_at = timezone.now()
    device.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': result.ok,
            'message': result.message,
            'serial_number': result.serial_number,
            'firmware': result.firmware,
            'user_count': result.user_count,
            'attendance_count': result.attendance_count,
        })

    if result.ok:
        messages.success(request, result.message)
    else:
        messages.error(request, result.message)
    return redirect('web:biometric_devices')


@permission_required('attendance.manage')
@require_POST
def biometric_device_sync(request, device_id):
    device = get_device_for_user(request.user, device_id)
    if not device.branch_id:
        messages.error(request, f'حدّد فرعاً لجهاز «{device.name}» قبل المزامنة.')
        return redirect('web:biometric_devices')
    queued, queue_msg = queue_lan_device_sync(device, requested_by_id=request.user.pk)
    if queued:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'queued': True, 'message': queue_msg})
        messages.success(request, queue_msg)
        return redirect('web:biometric_devices')

    outcome = sync_device_attendance(device, clear_after=False, force_mock=False)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(outcome)

    if outcome.get('ok'):
        users_part = ''
        if outcome.get('users_synced'):
            users_part = f' — {outcome["users_synced"]} مستخدم على الجهاز'
        skipped_time = outcome.get('skipped_time_filter', 0)
        time_part = f' — قديم {skipped_time}' if skipped_time else ''
        messages.success(
            request,
            f'جديد {outcome.get("punches_new", 0)} — مستورد {outcome.get("imported", 0)} '
            f'(تخطي {outcome.get("skipped", 0)} مكرر){time_part}{users_part}.',
        )
    else:
        messages.error(request, outcome.get('error', 'فشلت المزامنة.'))
    return redirect('web:biometric_devices')


@permission_required('attendance.manage')
@require_POST
def biometric_device_sync_users(request, device_id):
    device = get_device_for_user(request.user, device_id)
    queued, queue_msg = queue_lan_device_sync(device, requested_by_id=request.user.pk)
    if queued:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'queued': True, 'message': queue_msg})
        messages.success(request, queue_msg)
        return redirect('web:biometric_devices')

    outcome = sync_device_users(device, force_mock=False)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(outcome)

    if outcome.get('ok'):
        messages.success(request, f'تم سحب {outcome.get("synced", 0)} مستخدم من الجهاز.')
    else:
        messages.error(request, outcome.get('error', 'فشل سحب المستخدمين.'))
    return redirect('web:biometric_devices')


@permission_required('attendance.manage')
@require_POST
def biometric_enrollment_save(request):
    employee_id = request.POST.get('employee_id')
    device_id = request.POST.get('device_id')
    device_user_id = request.POST.get('device_user_id')

    if not all([employee_id, device_id, device_user_id]):
        messages.error(request, 'اختر الموظف والجهاز ورقم المستخدم على الجهاز.')
        return redirect('web:biometric_devices')

    device_user_name = ''
    try:
        du = BiometricDeviceUser.objects.get(
            device_id=device_id,
            device_user_id=int(device_user_id),
            is_deleted=False,
        )
        device_user_name = du.name
    except BiometricDeviceUser.DoesNotExist:
        pass

    employee = filter_employees_queryset_for_user(
        request.user,
        Employee.objects.filter(pk=employee_id, is_deleted=False),
    ).first()
    if not employee:
        messages.error(request, 'الموظف غير موجود أو ليس لديك صلاحية عليه.')
        return redirect('web:biometric_devices')

    device = get_device_for_user(request.user, int(device_id))
    if not device.branch_id:
        messages.error(request, 'يجب تعيين فرع للجهاز قبل الربط.')
        return redirect('web:biometric_devices')
    if employee.branch_id and device.branch_id and employee.branch_id != device.branch_id:
        messages.error(
            request,
            f'الموظف تابع لفرع «{employee.branch.name}» والجهاز لفرع «{device.branch.name}» — يجب أن يتطابقا.',
        )
        return redirect('web:biometric_devices')

    if not employee.branch_id and device.branch_id:
        employee.branch_id = device.branch_id
        employee.save(update_fields=['branch_id', 'updated_at'])

    existing_user_link = (
        EmployeeBiometricEnrollment.objects.filter(
            device_id=device_id,
            device_user_id=int(device_user_id),
            is_deleted=False,
        )
        .exclude(employee_id=employee_id)
        .select_related('employee')
        .first()
    )
    if existing_user_link:
        messages.error(
            request,
            f'رقم المستخدم {device_user_id} مربوط مسبقاً بالموظف «{existing_user_link.employee.name}».',
        )
        return redirect('web:biometric_devices')

    EmployeeBiometricEnrollment.objects.update_or_create(
        device_id=device_id,
        device_user_id=int(device_user_id),
        defaults={
            'employee_id': employee_id,
            'device_user_name': device_user_name,
            'is_deleted': False,
        },
    )

    AttendancePunch.objects.filter(
        device_id=device_id,
        device_user_id=int(device_user_id),
        is_deleted=False,
    ).update(
        employee_id=employee_id,
        device_user_name=device_user_name,
    )
    messages.success(
        request,
        f'تم ربط «{employee.name}» برقم {device_user_id} على الجهاز.',
    )
    from django.urls import reverse
    return redirect('web:biometric_devices')
