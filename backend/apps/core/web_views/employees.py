"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.core.models import Branch
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.web_views._helpers import (
    employee_branch_access_required,
    filter_employees_queryset_for_user,
    general_manager_required,
)
from apps.core.decorators import permission_required
from apps.core.salary_access import EMPLOYEE_SALARY_FIELD_NAMES, user_can_edit_salary


def _buildings_qs():
    from apps.setup.models import Building
    return Building.objects.filter(is_active=True, is_deleted=False).order_by('name')


def _banks_qs():
    from apps.setup.models import Bank
    return Bank.objects.filter(is_active=True, is_deleted=False).order_by('name')


def _administrations_qs():
    from apps.setup.models import Administration
    return Administration.objects.filter(is_active=True, is_deleted=False).order_by('code', 'name')


_EMPLOYEE_DOC_FIELDS = (
    'id_document', 'passport_document', 'contract_document',
    'other_documents', 'commencement_document',
)


def _prepare_employee_upload_files(request):
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    files = request.FILES.copy()
    for field_name in _EMPLOYEE_DOC_FIELDS:
        renamed = apply_uploaded_file_rename(request, field_name)
        if renamed is not None:
            files[field_name] = renamed
    return files


def _employee_post_tries_termination(request) -> bool:
    """رفض محاولات إنهاء الخدمة عبر نموذج التعديل المباشر."""
    from apps.employees.models import Employee

    if 'status' in request.POST:
        posted = (request.POST.get('status') or '').strip()
        if posted and posted != Employee.Status.ACTIVE and posted != Employee.Status.LEAVE:
            return True
    if (request.POST.get('end_date') or '').strip():
        return True
    if (request.POST.get('end_reason') or '').strip():
        return True
    return False


def _save_employee_from_form(request, form):
    from apps.core.services.file_helpers import apply_employee_document_renames

    employee = form.save()
    updated = apply_employee_document_renames(employee, request)
    if updated:
        employee.save(update_fields=[*updated, 'updated_at'])
    return employee


def _employee_edit_page_context(employee, *, form=None, is_create=False, user=None, requested_tab=None):
    from apps.setup.models import Nationality, Profession, Sponsorship, Insurance, InsuranceClass
    from apps.employees.services.contract_rules import saudi_nationality_ids
    from apps.core.employee_tab_permissions import enrich_employee_page_context

    ctx = {
        'employee': form.instance if form is not None else employee,
        'form': form,
        'is_create': is_create,
        'saudi_nationality_ids': saudi_nationality_ids(),
        'nationalities': Nationality.objects.filter(is_active=True),
        'professions': Profession.objects.filter(is_active=True),
        'sponsorships': Sponsorship.objects.filter(is_active=True),
        'branches': Branch.objects.filter(is_active=True),
        'departments': Department.objects.all(),
        'cost_centers': CostCenter.objects.all(),
        'insurances': Insurance.objects.filter(is_active=True),
        'insurance_classes': InsuranceClass.objects.filter(is_active=True),
        'buildings': _buildings_qs(),
        'banks': _banks_qs(),
        'administrations': _administrations_qs(),
    }
    if user is not None:
        enrich_employee_page_context(user, ctx, requested_tab=requested_tab, edit_form=True)
        ctx['can_edit_salary'] = user_can_edit_salary(user)
    return ctx


def _employee_edit_redirect(employee_id, *, tab: str | None = None):
    url = reverse('web:edit_employee', kwargs={'employee_id': employee_id})
    tab = (tab or '').strip()
    if tab:
        return redirect(f'{url}?tab={tab}')
    return redirect(url)


@login_required
@permission_required('employees.view')
def employee_picker_search(request):
    """بحث موظفين لاختيار الواجهة — JSON (مشترك بين النماذج والبصمة والحضور)."""
    from django.http import JsonResponse
    from apps.core.selectors.employee_picker_search import search_employees_for_picker

    q = (request.GET.get('q') or '').strip()
    results = search_employees_for_picker(request.user, q)
    return JsonResponse({'results': results, 'total': len(results)})


@login_required
@permission_required('employees.view')
def list_employees(request):
    """قائمة الموظفين مع بحث ذكي وترقيم"""
    from apps.employees.models import Employee
    from django.db.models import Q
    from django.core.paginator import Paginator

    qs = Employee.objects.select_related(
        'branch', 'department', 'administration', 'cost_center', 'nationality', 'profession',
    ).all()
    qs = filter_employees_queryset_for_user(request.user, qs)

    q = (request.GET.get('q') or '').strip()
    if q:
        terms = [t for t in q.split() if t]
        cond = Q()
        for t in terms:
            cond &= (
                Q(name__icontains=t) |
                Q(id_number__icontains=t) |
                Q(phone__icontains=t) |
                Q(branch__name__icontains=t) |
                Q(department__name__icontains=t) |
                Q(cost_center__name__icontains=t) |
                Q(nationality__name__icontains=t) |
                Q(profession__name__icontains=t) |
                Q(status__icontains=t)
            )
        qs = qs.filter(cond)

    qs = qs.order_by('-id')
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    ctx = {
        'employees': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'query': q,
        'total_count': paginator.count,
    }
    return render(request, 'pages/employees/list.html', ctx)


@login_required
@permission_required('employees.add')
def add_employee(request):
    """إنشاء طلب توظيف جديد (يحتاج موافقة الخط الأول)."""
    from apps.employees.forms import EmploymentRequestForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    if request.method == 'POST':
        # استبدال الملف بعد تطبيق إعادة التسمية
        files = request.FILES.copy()
        renamed = apply_uploaded_file_rename(request, 'commencement_document')
        if renamed is not None:
            files['commencement_document'] = renamed
        form = EmploymentRequestForm(request.POST, files, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.requested_by = request.user
            obj.save()
            messages.success(request, f'تم إرسال طلب توظيف "{obj.name}" إلى مدير الإدارة/الفرع للمراجعة')
            return redirect('web:list_employment_requests')
        for err in form.errors.values():
            messages.error(request, err[0])

    from apps.core.services.access_control import filter_branches_queryset

    return render(request, 'pages/employees/form.html', {
        'branches': filter_branches_queryset(request.user, Branch.objects.filter(is_active=True)),
        'departments': Department.objects.all(),
        'cost_centers': CostCenter.objects.all(),
        'administrations': _administrations_qs(),
    })


# =============================================================================
# Employment Requests (مدير الفرع)
# =============================================================================
@login_required
@permission_required('employees.add')
@general_manager_required
def create_employee_full(request):
    """إنشاء موظف مباشرة عبر النموذج الرئيسي الكامل (7 تبويبات)"""
    from apps.employees.models import Employee
    from apps.employees.forms import EmployeeForm

    if request.method == 'POST':
        files = _prepare_employee_upload_files(request)
        form = EmployeeForm(request.POST, files, user=request.user)
        if form.is_valid():
            if not user_can_edit_salary(request.user):
                for field_name in EMPLOYEE_SALARY_FIELD_NAMES:
                    if field_name in form.cleaned_data:
                        form.cleaned_data[field_name] = getattr(Employee(), field_name)
            emp = _save_employee_from_form(request, form)
            messages.success(request, f'تم إضافة الموظف "{emp.name}" بنجاح')
            return redirect('web:edit_employee', employee_id=emp.id)
        for field, errors in form.errors.items():
            messages.error(request, f'{field}: {errors[0]}')
        return render(
            request,
            'pages/employees/edit.html',
            _employee_edit_page_context(Employee(), form=form, is_create=True, user=request.user),
        )

    return render(
        request,
        'pages/employees/edit.html',
        _employee_edit_page_context(Employee(), is_create=True, user=request.user),
    )


@login_required
@permission_required('employees.view')
@employee_branch_access_required
def view_employee(request, employee_id):
    """عرض بيانات موظف — تحميل بيانات التبويب النشط فقط."""
    from apps.employees.models import Employee
    from apps.core.employee_tab_permissions import (
        employee_tab_visibility,
        enrich_employee_page_context,
    )
    from apps.employees.services.employee_view_data import (
        load_employee_view_context,
        resolve_active_employee_tab,
    )

    from django.db.models import Prefetch

    requested_tab = (request.GET.get('tab') or '').strip() or None
    tab_visible = employee_tab_visibility(request.user)
    active_tab = resolve_active_employee_tab(request.user, requested_tab)

    emp_qs = Employee.objects.select_related(
        'branch', 'department', 'administration', 'cost_center', 'nationality',
        'profession', 'sponsorship', 'insurance', 'insurance_class',
        'employment_request', 'employment_request__requested_by',
        'employment_request__reviewed_by',
    )
    stmt_tabs = {'warnings', 'archive', 'termination'}
    if stmt_tabs & {k for k, v in tab_visible.items() if v}:
        from apps.employees.models import EmployeeStatement
        emp_qs = emp_qs.prefetch_related(
            Prefetch(
                'statements_log',
                queryset=EmployeeStatement.objects.select_related('created_by').order_by(
                    '-statement_date', '-created_at',
                ),
            ),
        )
    employee = get_object_or_404(emp_qs, id=employee_id)

    tab_data = load_employee_view_context(
        employee=employee,
        user=request.user,
        active_tab=active_tab,
        tab_visible=tab_visible,
        request_get=request.GET,
        load_all_tabs=False,
    )

    ctx = enrich_employee_page_context(request.user, {
        'employee': employee,
        **tab_data,
    }, requested_tab=requested_tab)

    return render(request, 'pages/employees/view.html', ctx)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def save_employee_biometric_settings(request, employee_id):
    """حفظ وقت الدخول/الخروع وفترة تجاهل التأخير لتبويب البصمة."""
    from apps.employees.models import Employee
    from apps.attendance.services.employee_punch_display import get_or_create_biometric_settings

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    settings = get_or_create_biometric_settings(employee)

    def _parse_time(field: str):
        raw = (request.POST.get(field) or '').strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, '%H:%M').time()
        except ValueError:
            return None

    settings.expected_check_in = _parse_time('expected_check_in')
    settings.expected_check_out = _parse_time('expected_check_out')
    try:
        grace = int(request.POST.get('late_grace_minutes') or 30)
        settings.late_grace_minutes = max(0, min(grace, 180))
    except ValueError:
        settings.late_grace_minutes = 30
    settings.save(update_fields=[
        'expected_check_in', 'expected_check_out', 'late_grace_minutes', 'updated_at',
    ])
    messages.success(request, 'تم حفظ إعدادات البصمة.')

    from urllib.parse import urlencode
    params = {'tab': 'fingerprint'}
    if request.POST.get('fp_from'):
        params['fp_from'] = request.POST.get('fp_from')
    if request.POST.get('fp_to'):
        params['fp_to'] = request.POST.get('fp_to')
    url = reverse('web:view_employee', kwargs={'employee_id': employee.id})
    url = f'{url}?{urlencode(params)}#fingerprint'
    return redirect(url)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def edit_employee(request, employee_id):
    """تعديل ملف موظف - يكمل الأخصائي بقية الحقول"""
    from apps.employees.models import Employee
    from apps.employees.forms import EmployeeForm

    employee = get_object_or_404(
        Employee.objects.select_related(
            'branch', 'department', 'administration', 'cost_center', 'nationality',
            'profession', 'sponsorship', 'insurance', 'insurance_class', 'bank',
        ),
        id=employee_id,
    )

    if request.method == 'POST':
        files = _prepare_employee_upload_files(request)
        if _employee_post_tries_termination(request):
            messages.error(
                request,
                'تغيير حالة الموظف أو إنهاء الخدمة يتم عبر سير الموافقات فقط.',
            )
            return redirect('web:view_employee', employee_id=employee.id)

        form = EmployeeForm(request.POST, files, instance=employee, user=request.user)
        if form.is_valid():
            if not user_can_edit_salary(request.user):
                for field_name in EMPLOYEE_SALARY_FIELD_NAMES:
                    if field_name in form.cleaned_data:
                        form.cleaned_data[field_name] = getattr(employee, field_name)
            employee = _save_employee_from_form(request, form)
            messages.success(request, f'تم حفظ بيانات الموظف "{employee.name}"')
            return_tab = (request.POST.get('return_tab') or request.GET.get('tab') or '').strip()
            return _employee_edit_redirect(employee.id, tab=return_tab)
        for field, errors in form.errors.items():
            messages.error(request, f'{field}: {errors[0]}')
        return_tab = (request.POST.get('return_tab') or request.GET.get('tab') or '').strip()
        return render(
            request,
            'pages/employees/edit.html',
            _employee_edit_page_context(
                employee, form=form, user=request.user, requested_tab=return_tab or None,
            ),
        )

    requested_tab = (request.GET.get('tab') or '').strip() or None
    return render(
        request,
        'pages/employees/edit.html',
        _employee_edit_page_context(employee, user=request.user, requested_tab=requested_tab),
    )


@login_required
@permission_required('employees.delete')
@employee_branch_access_required
def delete_employee(request, employee_id):
    """حذف موظف (admin فقط)"""
    from apps.employees.models import Employee
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == 'POST':
        name = employee.name
        employee.delete()
        messages.success(request, f'تم حذف الموظف "{name}"')
    return redirect('web:list_employees')


