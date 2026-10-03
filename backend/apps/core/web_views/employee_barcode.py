"""طباعة ملصق باركود الموظف — Zebra بمقاسات قابلة للتعديل."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
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
    build_manual_barcode_label,
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

    from apps.setup.models import Sponsorship
    companies = list(
        Sponsorship.objects.filter(is_active=True, is_deleted=False)
        .exclude(company_name='')
        .order_by('company_name')
        .values_list('company_name', flat=True)
        .distinct()
    )

    return render(request, 'pages/employees/barcode_labels_index.html', {
        'sponsor_companies': companies,
        'initial_mode': 'manual' if request.GET.get('mode') == 'manual' else 'employee',
        'manual_name': (request.GET.get('name') or '')[:120],
        'manual_number': (request.GET.get('number') or '')[:48],
        'manual_company': (request.GET.get('company') or '')[:200],
        'manual_print_url': reverse('web:employee_barcode_manual_print'),
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


def _manual_label_from_request(request, dims):
    return build_manual_barcode_label(
        name=(request.GET.get('name') or '')[:120],
        employee_number=(request.GET.get('number') or '')[:48],
        company_name=(request.GET.get('company') or '')[:200],
        dims=dims,
    )


def _manual_extra(request) -> dict:
    return {
        'name': (request.GET.get('name') or '')[:120],
        'number': (request.GET.get('number') or '')[:48],
        'company': (request.GET.get('company') or '')[:200],
    }


@login_required
@permission_required('employees.view')
def employee_barcode_manual_print(request):
    """معاينة وطباعة ملصق بإدخال يدوي."""
    dims, copies = _dims_from_request(request)
    label = _manual_label_from_request(request, dims)
    extra = _manual_extra(request)
    size_qs = label_size_querystring(dims, copies=copies, extra=extra)
    return render(request, 'pages/employees/barcode_label_print.html', {
        'employee': None,
        'label': label,
        'label_dims': dims,
        'copies': copies,
        'copy_range': range(copies),
        'zpl_download_url': f"{reverse('web:employee_barcode_manual_zpl')}?{size_qs}",
        'size_querystring': size_qs,
        'back_url': f"{reverse('web:employee_barcode_labels')}?{size_qs}&mode=manual",
        'hidden_params': extra,
    })


@login_required
@permission_required('employees.view')
def employee_barcode_manual_zpl(request):
    """تنزيل ZPL للملصق اليدوي."""
    dims, copies = _dims_from_request(request)
    label = _manual_label_from_request(request, dims)
    zpl = build_zpl_label(label, dims=dims, copies=copies)
    response = HttpResponse(zpl, content_type='application/octet-stream')
    response['Content-Disposition'] = 'attachment; filename="employee-name-manual.zpl"'
    return response


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
