"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
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


def _buildings_qs():
    from apps.setup.models import Building
    return Building.objects.filter(is_active=True, is_deleted=False).order_by('name')


def _banks_qs():
    from apps.setup.models import Bank
    return Bank.objects.filter(is_active=True, is_deleted=False).order_by('name')

@login_required
@permission_required('employees.view')
def list_employees(request):
    """قائمة الموظفين مع بحث ذكي وترقيم"""
    from apps.employees.models import Employee
    from django.db.models import Q
    from django.core.paginator import Paginator

    qs = Employee.objects.select_related(
        'branch', 'department', 'cost_center', 'nationality'
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

    return render(request, 'pages/employees/list.html', {
        'employees': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'query': q,
        'total_count': paginator.count,
    })


@login_required
@permission_required('employees.add')
def add_employee(request):
    """إنشاء طلب توظيف جديد (يحتاج موافقة مدير الفرع)"""
    from apps.employees.forms import EmploymentRequestForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    if request.method == 'POST':
        # استبدال الملف بعد تطبيق إعادة التسمية
        files = request.FILES.copy()
        renamed = apply_uploaded_file_rename(request, 'commencement_document')
        if renamed is not None:
            files['commencement_document'] = renamed
        form = EmploymentRequestForm(request.POST, files)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.requested_by = request.user
            obj.save()
            messages.success(request, f'تم إرسال طلب توظيف "{obj.name}" إلى مدير الفرع للمراجعة')
            return redirect('web:list_employment_requests')
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/employees/form.html', {
        'branches': Branch.objects.filter(is_active=True),
        'departments': Department.objects.all(),
        'cost_centers': CostCenter.objects.all(),
    })


# =============================================================================
# Employment Requests (مدير الفرع)
# =============================================================================
@login_required
@permission_required('employees.add')
@general_manager_required
def create_employee_full(request):
    """إنشاء موظف مباشرة عبر النموذج الرئيسي الكامل (7 تبويبات)"""
    from apps.setup.models import Nationality, Profession, Sponsorship, Insurance, InsuranceClass
    from apps.employees.models import Employee
    from apps.employees.forms import EmployeeForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    if request.method == 'POST':
        # تطبيق إعادة تسمية الملفات قبل تمريرها للـ form
        files = request.FILES.copy()
        for f in ('id_document', 'passport_document', 'contract_document',
                  'other_documents', 'commencement_document'):
            renamed = apply_uploaded_file_rename(request, f)
            if renamed is not None:
                files[f] = renamed

        form = EmployeeForm(request.POST, files)
        if form.is_valid():
            emp = form.save()
            messages.success(request, f'تم إضافة الموظف "{emp.name}" بنجاح')
            return redirect('web:list_employees')
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/employees/edit.html', {
        'employee': Employee(),  # كائن فارغ لإعادة استخدام نفس القالب
        'is_create': True,
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
    })


@login_required
@permission_required('employees.view')
@employee_branch_access_required
def view_employee(request, employee_id):
    """عرض بيانات موظف للقراءة فقط"""
    from apps.employees.models import Employee
    from apps.departments.models import Department
    from apps.core.models import Branch

    employee = get_object_or_404(
        Employee.objects.select_related(
            'branch', 'department', 'cost_center', 'nationality',
            'profession', 'sponsorship', 'insurance', 'insurance_class',
            'employment_request', 'employment_request__requested_by',
            'employment_request__reviewed_by',
        ),
        id=employee_id,
    )
    departments = Department.objects.order_by('name')
    branches = Branch.objects.order_by('name')
    statements_count = employee.statements_log.filter(
        statement_type__in=['statement', 'warning', 'final_warning', 'acknowledgment', 'other']
    ).count()
    salary_adjusts = employee.statements_log.filter(
        statement_type='salary_adjust'
    ).select_related('created_by').order_by('-statement_date', '-created_at')

    # توقّع الرقم المتسلسل التالي للإفادات (للمعاينة في النموذج)
    from apps.employees.models import EmployeeStatement
    next_statement_serial = EmployeeStatement.generate_serial('statement')

    # جدول الدوام: قراءة JSON كصناديق شهرية
    import json as _json
    schedule_boxes = []
    try:
        _data = _json.loads(employee.work_schedule or '') if employee.work_schedule else None
        if isinstance(_data, dict) and isinstance(_data.get('boxes'), list):
            schedule_boxes = _data['boxes']
    except (ValueError, TypeError):
        schedule_boxes = []

    # Custodies / Business Trips / Job Offers / Accruals (historical tabs)
    custodies = employee.custodies.all().order_by('-received_at', '-id')
    active_custodies = employee.custodies.filter(status='active').order_by('-received_at')
    business_trips = employee.business_trips.all().order_by('-start_date', '-id')
    job_offers = employee.job_offers.all().order_by('-issued_at', '-id')
    loans = employee.loans.all().order_by('-issued_at', '-id')
    absences = employee.absences.all().order_by('-absence_date', '-id')
    
    # Ledger accruals — تهيئة تلقائية إذا لم يكن هناك سجل
    accruals = []
    try:
        from apps.employees.models import EmployeeLedger
        from decimal import Decimal
        from django.utils import timezone

        accruals_qs = employee.accruals_ledger.all().order_by('-date', '-created_at')

        # تهيئة تلقائية: إذا لم يكن هناك أي سجل وعنده تاريخ مباشرة
        if not accruals_qs.exists() and employee.hire_date:
            today = timezone.now().date()
            service_days = (today - employee.hire_date).days
            if service_days >= 1:
                service_years = Decimal(str(round(service_days / 365.25, 4)))
                leave_days = (Decimal(str(service_days)) * Decimal('21') / Decimal('365.25')).quantize(Decimal('0.01'))
                total_salary = Decimal(str(employee.total_salary or 0))
                daily_wage = (total_salary / Decimal('30')).quantize(Decimal('0.01'))
                leave_amount = (leave_days * daily_wage).quantize(Decimal('0.01'))

                half_salary = (total_salary / Decimal('2')).quantize(Decimal('0.01'))
                if service_years <= 5:
                    eosb = (half_salary * service_years).quantize(Decimal('0.01'))
                    eosb_detail = f'نصف الراتب × سنوات الخدمة = {half_salary} × {service_years} = {eosb}'
                else:
                    first5 = (half_salary * Decimal('5')).quantize(Decimal('0.01'))
                    extra_yrs = (service_years - Decimal('5')).quantize(Decimal('0.0001'))
                    extra_amt = (total_salary * extra_yrs).quantize(Decimal('0.01'))
                    eosb = (first5 + extra_amt).quantize(Decimal('0.01'))
                    eosb_detail = f'أول 5 سنوات: {half_salary} × 5 = {first5} | بعد 5 سنوات: {total_salary} × {extra_yrs} = {extra_amt} | الإجمالي = {eosb}'

                from apps.employees.services.accrual_ledger_notes import build_initial_balance_notes
                notes = build_initial_balance_notes(
                    hire_date=employee.hire_date,
                    as_of_date=today,
                    total_salary=total_salary,
                    leave_days=leave_days,
                    leave_amount=leave_amount,
                    eosb=eosb,
                    eosb_detail=eosb_detail,
                )

                EmployeeLedger.objects.create(
                    employee=employee,
                    transaction_type='initial',
                    date=today,
                    leave_days_change=leave_days,
                    leave_amount_change=leave_amount,
                    eosb_amount_change=eosb,
                    cumulative_leave_days=leave_days,
                    cumulative_leave_amount=leave_amount,
                    cumulative_eosb_amount=eosb,
                    notes=notes,
                    created_by=request.user
                )

        accruals = list(
            employee.accruals_ledger.select_related('payroll_run', 'employee')
            .all()
            .order_by('-date', '-created_at')
        )
    except Exception:
        accruals = []

    return render(request, 'pages/employees/view.html', {
        'employee': employee,
        'departments': departments,
        'branches': branches,
        'statements_count': statements_count,
        'next_statement_serial': next_statement_serial,
        'schedule_boxes_json': schedule_boxes,
        'salary_adjusts': salary_adjusts,
        'custodies': custodies,
        'active_custodies': active_custodies,
        'business_trips': business_trips,
        'job_offers': job_offers,
        'loans': loans,
        'absences': absences,
        'accruals': accruals,
    })


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def edit_employee(request, employee_id):
    """تعديل ملف موظف - يكمل الأخصائي بقية الحقول"""
    from apps.setup.models import Nationality, Profession, Sponsorship, Insurance, InsuranceClass
    from apps.employees.models import Employee
    from apps.employees.forms import EmployeeForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)

    if request.method == 'POST':
        files = request.FILES.copy()
        for f in ('id_document', 'passport_document', 'contract_document',
                  'other_documents', 'commencement_document'):
            renamed = apply_uploaded_file_rename(request, f)
            if renamed is not None:
                files[f] = renamed

        form = EmployeeForm(request.POST, files, instance=employee)
        if form.is_valid():
            employee = form.save()
            messages.success(request, f'تم حفظ بيانات الموظف "{employee.name}"')
            return redirect('web:list_employees')
        
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/employees/edit.html', {
        'employee': employee,
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
    })


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


