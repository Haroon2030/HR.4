"""طباعة ملصق باركود الموظف — Zebra بمقاسات قابلة للتعديل."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.decorators import permission_required
from apps.core.web_views._helpers import (
    employee_branch_access_required,
    filter_employees_queryset_for_user,
)
from apps.employees.models import Employee
from apps.employees.services.barcode_label import (
    DEFAULT_LABEL_HEIGHT_MM,
    DEFAULT_LABEL_WIDTH_MM,
    MAX_LABEL_HEIGHT_MM,
    MAX_LABEL_WIDTH_MM,
    MIN_LABEL_HEIGHT_MM,
    MIN_LABEL_WIDTH_MM,
    build_employee_barcode_label,
    build_zpl_label,
    label_size_querystring,
    parse_copies,
    parse_label_dimensions,
)


def _employee_for_barcode(user, employee_id: int) -> Employee:
    qs = Employee.objects.filter(is_deleted=False).select_related(
        'branch', 'branch__company', 'department', 'sponsorship',
    )
    qs = filter_employees_queryset_for_user(user, qs)
    return get_object_or_404(qs, pk=employee_id)


def _dims_from_request(request) -> tuple:
    dims = parse_label_dimensions(request.GET.get('w'), request.GET.get('h'))
    copies = parse_copies(request.GET.get('copies'))
    return dims, copies


@login_required
@permission_required('employees.view')
def employee_barcode_labels_index(request):
    """شاشة اختيار موظف وطباعة ملصق الباركود."""
    preselected = None
    raw_id = (request.GET.get('employee_id') or '').strip()
    if raw_id.isdigit():
        emp = filter_employees_queryset_for_user(
            request.user,
            Employee.objects.filter(is_deleted=False, pk=int(raw_id)),
        ).first()
        if emp:
            preselected = emp

    dims = parse_label_dimensions(request.GET.get('w'), request.GET.get('h'))
    has_size_params = 'w' in request.GET or 'h' in request.GET

    return render(request, 'pages/employees/barcode_labels_index.html', {
        'employee_search_url': reverse('web:employee_picker_search'),
        'filter_employee': preselected,
        'default_copies': parse_copies(request.GET.get('copies'), default=1),
        'label_dims': dims,
        'url_has_size': has_size_params,
        'min_width_mm': MIN_LABEL_WIDTH_MM,
        'max_width_mm': MAX_LABEL_WIDTH_MM,
        'min_height_mm': MIN_LABEL_HEIGHT_MM,
        'max_height_mm': MAX_LABEL_HEIGHT_MM,
        'default_width_mm': DEFAULT_LABEL_WIDTH_MM,
        'default_height_mm': DEFAULT_LABEL_HEIGHT_MM,
    })


@login_required
@permission_required('employees.view')
@employee_branch_access_required
def employee_barcode_print(request, employee_id):
    """معاينة وطباعة ملصق بمقاس مخصص (متصفح / Zebra)."""
    employee = _employee_for_barcode(request.user, employee_id)
    dims, copies = _dims_from_request(request)
    label = build_employee_barcode_label(employee, dims=dims)
    size_qs = label_size_querystring(dims, copies=copies)
    zpl_url = (
        f"{reverse('web:employee_barcode_zpl', kwargs={'employee_id': employee.pk})}"
        f'?{size_qs}'
    )
    return render(request, 'pages/employees/barcode_label_print.html', {
        'employee': employee,
        'label': label,
        'label_dims': dims,
        'copies': copies,
        'copy_range': range(copies),
        'zpl_download_url': zpl_url,
        'size_querystring': size_qs,
    })


@login_required
@permission_required('employees.view')
@employee_branch_access_required
def employee_barcode_zpl(request, employee_id):
    """تنزيل ملف ZPL للإرسال المباشر لطابعة Zebra."""
    employee = _employee_for_barcode(request.user, employee_id)
    dims, copies = _dims_from_request(request)
    label = build_employee_barcode_label(employee, dims=dims)
    zpl = build_zpl_label(label, dims=dims, copies=copies)
    filename = f'employee-name-{employee.pk}.zpl'
    response = HttpResponse(zpl, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@permission_required('employees.view')
def employee_barcode_print_batch(request):
    """طباعة دفعة ملصقات لعدة موظفين (?ids=1,2,3&copies=1&w=100&h=40)."""
    raw = (request.GET.get('ids') or '').strip()
    if not raw:
        messages.error(request, 'حدّد موظفاً واحداً على الأقل.')
        return redirect('web:employee_barcode_labels')

    ids: list[int] = []
    for part in raw.split(','):
        s = part.strip()
        if s.isdigit():
            ids.append(int(s))
    ids = list(dict.fromkeys(ids))[:30]
    if not ids:
        messages.error(request, 'معرّفات الموظفين غير صالحة.')
        return redirect('web:employee_barcode_labels')

    dims, copies = _dims_from_request(request)
    qs = filter_employees_queryset_for_user(
        request.user,
        Employee.objects.filter(is_deleted=False, pk__in=ids).select_related(
            'branch', 'branch__company', 'sponsorship',
        ),
    )
    employees = list(qs.order_by('name'))
    if not employees:
        raise Http404('لم يُعثَر على موظفين.')

    labels = [build_employee_barcode_label(emp, dims=dims) for emp in employees]
    label_copies: list = []
    for lbl in labels:
        for _ in range(copies):
            label_copies.append(lbl)

    size_qs = label_size_querystring(dims, copies=copies)

    return render(request, 'pages/employees/barcode_label_print.html', {
        'employee': employees[0],
        'label': labels[0],
        'label_dims': dims,
        'labels_batch': label_copies,
        'copies': copies,
        'copy_range': range(copies),
        'batch_mode': True,
        'zpl_download_url': '',
        'size_querystring': size_qs,
    })
