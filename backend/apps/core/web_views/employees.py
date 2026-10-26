"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from datetime import datetime
import tempfile
import os

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.models import Branch
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department
from apps.employees.services.document_parser import extract_employment_contract_data
from apps.core.validators import validate_employee_upload


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
    from apps.core.services.setup_cache import get_cached_list

    ctx = {
        'employee': form.instance if form is not None else employee,
        'form': form,
        'is_create': is_create,
        'saudi_nationality_ids': saudi_nationality_ids(),
        'nationalities': get_cached_list(
            'nationalities',
            lambda: list(Nationality.objects.filter(is_active=True).order_by('name')),
        ),
        'professions': get_cached_list(
            'professions',
            lambda: list(Profession.objects.filter(is_active=True).order_by('name')),
        ),
        'sponsorships': get_cached_list(
            'sponsorships',
            lambda: list(Sponsorship.objects.filter(is_active=True).order_by('company_name')),
        ),
        'branches': get_cached_list(
            'active_branches',
            lambda: list(Branch.objects.filter(is_active=True, is_deleted=False).order_by('name')),
        ),
        'departments': get_cached_list(
            'departments_all',
            lambda: list(Department.objects.select_related('branch').order_by('name')),
        ),
        'cost_centers': get_cached_list(
            'cost_centers_all',
            lambda: list(CostCenter.objects.select_related('branch').order_by('name')),
        ),
        'insurances': get_cached_list(
            'insurances',
            lambda: list(Insurance.objects.filter(is_active=True).order_by('insurance_type')),
        ),
        'insurance_classes': get_cached_list(
            'insurance_classes',
            lambda: list(InsuranceClass.objects.filter(is_active=True).order_by('class_type')),
        ),
        'buildings': get_cached_list('buildings', _buildings_qs),
        'banks': get_cached_list('banks', _banks_qs),
        'administrations': get_cached_list('administrations', _administrations_qs),
    }
    if user is not None:
        from apps.core.services.access_control import get_scoped_administration_ids

        scoped_ids = get_scoped_administration_ids(user)
        if scoped_ids is not None:
            ctx['administrations'] = [a for a in ctx['administrations'] if a.pk in scoped_ids]
        enrich_employee_page_context(user, ctx, requested_tab=requested_tab, edit_form=True)
        ctx['can_edit_salary'] = user_can_edit_salary(user)
        ctx['employee_edit_client_tabs'] = True
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
    from django.core.paginator import Paginator
    from apps.core.selectors.employee_search import apply_employee_search

    qs = Employee.objects.select_related(
        'branch', 'department', 'administration', 'cost_center', 'nationality', 'profession',
    ).all()
    qs = filter_employees_queryset_for_user(request.user, qs)

    from apps.core.selectors.employee_filters import (
        active_filter_count,
        apply_employee_list_filters,
        employee_list_querystring,
        parse_employee_list_filters,
    )
    from apps.core.services.access_control import filter_branches_queryset
    from apps.departments.models import Department
    from apps.setup.models import Sponsorship

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = apply_employee_search(qs, q)
    filters = parse_employee_list_filters(request.GET)
    qs = apply_employee_list_filters(qs, filters)

    qs = qs.order_by('-id')
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    from django.urls import reverse

    filter_qs = employee_list_querystring(q, filters)
    export_url = reverse('web:export_non_sponsored_employees_excel')
    sponsored_export_url = reverse('web:export_sponsored_employees_excel')
    if filter_qs:
        export_url = f'{export_url}?{filter_qs}'
        sponsored_export_url = f'{sponsored_export_url}?{filter_qs}'

    ctx = {
        'employees': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'query': q,
        'total_count': paginator.count,
        'no_sponsorship_export_url': export_url,
        'no_sponsorship_import_url': reverse('web:import_non_sponsored_employees_excel'),
        'sponsorship_import_url': reverse('web:import_sponsored_employees_excel'),
        'sponsorship_export_url': sponsored_export_url,
        'filters': filters,
        'filter_qs': filter_qs,
        'active_filters': active_filter_count(q, filters),
        'filter_branches': filter_branches_queryset(
            request.user, Branch.objects.filter(is_active=True, is_deleted=False),
        ).order_by('name'),
        'filter_departments': Department.objects.filter(
            is_active=True, is_deleted=False,
        ).order_by('name'),
        'filter_sponsorships': Sponsorship.objects.filter(
            is_active=True, is_deleted=False,
        ).order_by('company_name'),
    }
    return render(request, 'pages/employees/list.html', ctx)


@login_required
@permission_required('employees.add')
def add_employee(request):
    """إنشاء طلب توظيف جديد (يحتاج موافقة الخط الأول)."""
    from apps.employees.forms import EmploymentRequestForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename
    from apps.setup.models import Nationality, Sponsorship

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
            from apps.core.services.employment_requests import skip_first_stage_if_unrouted
            if skip_first_stage_if_unrouted(obj):
                messages.success(
                    request,
                    f'تم إرسال طلب توظيف "{obj.name}" إلى مدير الموارد مباشرة (لا يوجد مدير إدارة/فرع محدَّد)',
                )
            else:
                messages.success(request, f'تم إرسال طلب توظيف "{obj.name}" إلى مدير الإدارة/الفرع للمراجعة')
            return redirect('web:list_pending_actions')
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/employees/form.html', employment_request_form_context(request.user))


def employment_request_form_context(user, **extra):
    """سياق نموذج طلب التوظيف (الإضافة وتعديل الطلب المُرتجَع)."""
    from apps.core.services.access_control import (
        filter_administrations_for_user,
        filter_branches_queryset,
        get_scoped_administration_ids,
    )
    from apps.setup.models import Nationality, Sponsorship

    administrations = list(filter_administrations_for_user(user, _administrations_qs()))
    administration_locked = get_scoped_administration_ids(user) is not None
    default_administration_id = (
        administrations[0].pk if administration_locked and len(administrations) == 1 else None
    )
    return {
        'branches': filter_branches_queryset(user, Branch.objects.filter(is_active=True)),
        'departments': Department.objects.all(),
        'cost_centers': CostCenter.objects.all(),
        'sponsorships': Sponsorship.objects.filter(is_active=True).order_by('company_name'),
        'nationalities': Nationality.objects.filter(is_active=True).order_by('name'),
        'administrations': administrations,
        'administration_locked': administration_locked,
        'default_administration_id': default_administration_id,
        'doc_required': True,  # مستند المباشرة إلزامي عند الإضافة
        **extra,
    }


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

    from apps.employees.services.suspension import user_can_suspend_employees

    ctx = enrich_employee_page_context(request.user, {
        'employee': employee,
        'can_suspend_employee': user_can_suspend_employees(request.user),
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
def save_employee_leave_settings(request, employee_id):
    """حفظ الرصيد الافتتاحي وتاريخ الاحتساب من تبويب الإجازات."""
    from decimal import Decimal, InvalidOperation
    from apps.employees.models import Employee

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves')

    def _parse_decimal(raw, *, field_label: str) -> Decimal | None:
        text = (raw or '').strip()
        if not text:
            return Decimal('0')
        try:
            return Decimal(text).quantize(Decimal('0.01'))
        except InvalidOperation:
            messages.error(request, f'قيمة غير صالحة في {field_label}.')
            return None

    def _parse_date(raw):
        text = (raw or '').strip()
        if not text:
            return None
        try:
            return datetime.strptime(text[:10], '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'تاريخ الاحتساب غير صالح.')
            return False

    opening = _parse_decimal(request.POST.get('opening_leave_days'), field_label='الرصيد الافتتاحي')
    if opening is None:
        return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves')

    accrual_start = _parse_date(request.POST.get('leave_accrual_start_date'))
    if accrual_start is False:
        return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves')

    if opening > 0 and not accrual_start:
        messages.error(request, 'أدخل تاريخ الاحتساب عند تعبئة رصيد افتتاحي.')
        return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves')

    accrual_end = _parse_date(request.POST.get('leave_accrual_end_date'))
    if accrual_end is False:
        return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves')
    if accrual_end and accrual_start and accrual_end < accrual_start:
        messages.error(request, 'تاريخ نهاية الاحتساب يجب أن يكون بعد تاريخ البداية.')
        return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves')

    annual_raw = (request.POST.get('annual_leave_days') or '').strip()
    valid_annual = {value for value, _ in Employee.ANNUAL_LEAVE_DAYS_CHOICES}
    if annual_raw and (not annual_raw.isdigit() or int(annual_raw) not in valid_annual):
        messages.error(request, 'أيام الإجازة السنوية يجب أن تكون بين 21 و30.')
        return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves')

    update_fields = ['opening_leave_days', 'leave_accrual_start_date', 'leave_accrual_end_date', 'updated_at']
    if annual_raw:
        employee.annual_leave_days = int(annual_raw)
        update_fields.append('annual_leave_days')
    employee.opening_leave_days = opening
    employee.leave_accrual_start_date = accrual_start
    employee.leave_accrual_end_date = accrual_end if accrual_start else None

    if not accrual_start:
        used = _parse_decimal(
            request.POST.get('available_leave_balance'),
            field_label='الإجازات المستخدمة',
        )
        if used is None:
            return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves')
        employee.available_leave_balance = used
        update_fields.append('available_leave_balance')

    employee.save(update_fields=update_fields)
    messages.success(request, 'تم حفظ إعدادات رصيد الإجازة.')
    return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee.id})}?tab=leaves#employee-tab-panel')


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def edit_employee(request, employee_id):
    """تعديل ملف موظف - يكمل الأخصائي بقية الحقول"""
    from django.db.models import Prefetch
    from apps.employees.models import Employee, EmployeeStatement
    from apps.employees.forms import EmployeeForm

    employee = get_object_or_404(
        Employee.objects.select_related(
            'branch', 'department', 'administration', 'cost_center', 'nationality',
            'profession', 'sponsorship', 'insurance', 'insurance_class', 'bank',
            'employment_request', 'employment_request__requested_by',
            'employment_request__reviewed_by',
        ).prefetch_related(
            Prefetch(
                'statements_log',
                queryset=EmployeeStatement.objects.select_related('created_by').order_by(
                    '-statement_date', '-id',
                ),
            ),
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


# =============================================================================
# استخراج البيانات من عقد التوظيف
# =============================================================================

@login_required
@require_http_methods(['POST'])
def parse_employment_contract(request):
    """
    API endpoint لاستخراج البيانات من عقد توظيف PDF.

    POST /employees/parse-contract/
    Content-Type: multipart/form-data
    File: commencement_document (PDF)

    الرد:
    {
        'success': bool,
        'error': str | None,
        'data': {...},
        'warnings': [str]
    }
    """
    # ميزة محصورة بالسوبر أدمن (الزر مخفي لغيره، والفحص هنا يمنع الاستدعاء المباشر)
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'غير مصرّح', 'data': None, 'warnings': []}, status=403)

    if 'commencement_document' not in request.FILES:
        return JsonResponse({
            'success': False,
            'error': 'لم يتم رفع ملف',
            'data': None,
            'warnings': []
        }, status=400)

    file_obj = request.FILES['commencement_document']

    # التحقق من الملف
    try:
        validate_employee_upload(file_obj)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'data': None,
            'warnings': []
        }, status=400)

    # حفظ الملف مؤقتاً واستخراج البيانات
    temp_file = None
    try:
        # إنشاء ملف مؤقت
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            for chunk in file_obj.chunks():
                tmp.write(chunk)
            temp_file = tmp.name

        # استخراج البيانات
        result = extract_employment_contract_data(temp_file, file_obj.name)

        if result['data']:
            result['data']['nationality_id'] = _resolve_nationality_id(result['data'].get('nationality'))

        # تحويل Decimal إلى str للـ JSON
        if result['data']:
            result['data'] = _convert_decimals_for_json(result['data'])

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في معالجة الملف: {str(e)}',
            'data': None,
            'warnings': []
        }, status=500)

    finally:
        # حذف الملف المؤقت
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except:
                pass


def _resolve_nationality_id(label):
    """ربط جنسية العقد (مثل Saudi) بسجل الجنسية في جدول الإعداد."""
    from apps.employees.services.document_parser import NATIONALITY_EN_TO_AR
    from apps.setup.models import Nationality
    if not label:
        return None
    arabic = NATIONALITY_EN_TO_AR.get(label.strip().lower(), label.strip())
    row = Nationality.objects.filter(is_active=True, is_deleted=False, name=arabic).first()
    return row.id if row else None


def _convert_decimals_for_json(data: dict) -> dict:
    """تحويل Decimal إلى str لـ JSON serialization."""
    from decimal import Decimal

    for key, value in data.items():
        if isinstance(value, Decimal):
            data[key] = str(value)
        elif isinstance(value, dict):
            data[key] = _convert_decimals_for_json(value)

    return data

