"""
واجهات مسير الرواتب الشهري.
"""
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse, Http404
from django.db.models import Sum, Count

from apps.core.decorators import permission_required
from apps.core.models import Branch
from apps.payroll.models import PayrollRun, PayrollLine
from apps.payroll.services.engine import (
    build_payroll_run, lock_payroll_run, unlock_payroll_run,
)


def _user_branches(user):
    """يعيد فروع المستخدم (أو كل الفروع للسوبر يوزر / مدير الموارد)."""
    from apps.core.models import Role
    if user.is_superuser:
        return Branch.objects.filter(is_active=True).order_by('name')

    profile = getattr(user, 'profile', None)
    # Admin / HR_MANAGER → كل الفروع
    if profile and profile.role and profile.role.role_type in (
        Role.RoleType.ADMIN, Role.RoleType.HR_MANAGER,
    ):
        return Branch.objects.filter(is_active=True).order_by('name')

    # باقي المستخدمين: فرعه + الفروع التي يديرها + المُسندة إليه
    from django.db.models import Q
    branch_ids = set()
    if profile:
        if profile.branch_id:
            branch_ids.add(profile.branch_id)
        branch_ids.update(profile.assigned_branches.values_list('id', flat=True))
    branch_ids.update(user.managed_branches.values_list('id', flat=True))

    if branch_ids:
        return Branch.objects.filter(id__in=branch_ids, is_active=True).order_by('name')
    return Branch.objects.none()


@login_required
@permission_required('employees.view')
def list_payroll_runs(request):
    """قائمة المسيرات."""
    qs = PayrollRun.objects.select_related('branch', 'created_by', 'locked_by')
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser:
        qs = qs.filter(branch__in=user_branches)

    # فلاتر
    year = request.GET.get('year')
    month = request.GET.get('month')
    branch_id = request.GET.get('branch')
    status = request.GET.get('status')
    if year:
        qs = qs.filter(period_year=year)
    if month:
        qs = qs.filter(period_month=month)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if status:
        qs = qs.filter(status=status)

    from django.core.paginator import Paginator
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    today = date.today()
    return render(request, 'pages/payroll/list.html', {
        'runs': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'branches': user_branches,
        'current_year': today.year,
        'current_month': today.month,
        'years_range': range(today.year - 2, today.year + 1),
        'months_range': range(1, 13),
        'filter_year': year, 'filter_month': month,
        'filter_branch': branch_id, 'filter_status': status,
        'STATUS_CHOICES': PayrollRun.Status.choices,
    })


@login_required
@permission_required('employees.edit')
def create_payroll_run(request):
    """إنشاء/إعادة بناء مسير لشهر وفرع محددين."""
    if request.method != 'POST':
        return redirect('web:list_payroll_runs')

    try:
        branch_id = int(request.POST.get('branch_id') or 0)
        year = int(request.POST.get('year') or 0)
        month = int(request.POST.get('month') or 0)
    except ValueError:
        messages.error(request, 'بيانات غير صحيحة.')
        return redirect('web:list_payroll_runs')

    if not (branch_id and 2020 <= year <= 2100 and 1 <= month <= 12):
        messages.error(request, 'يرجى تحديد الفرع والسنة والشهر.')
        return redirect('web:list_payroll_runs')

    branch = get_object_or_404(Branch, id=branch_id)
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and branch not in user_branches:
        messages.error(request, 'لا تملك صلاحية على هذا الفرع.')
        return redirect('web:list_payroll_runs')

    try:
        run = build_payroll_run(branch, year, month, request.user)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('web:list_payroll_runs')

    messages.success(request, f'تم بناء المسير لـ {branch.name} — {run.period_label} ({run.employees_count} موظف).')
    return redirect('web:view_payroll_run', run_id=run.id)


@login_required
@permission_required('employees.view')
def view_payroll_run(request, run_id):
    """عرض تفاصيل مسير."""
    run = get_object_or_404(
        PayrollRun.objects.select_related('branch', 'created_by', 'locked_by'),
        id=run_id
    )
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()

    lines = run.lines.select_related('employee').order_by('employee__name')
    return render(request, 'pages/payroll/view.html', {
        'run': run,
        'lines': lines,
    })


@login_required
@permission_required('employees.edit')
def rebuild_payroll_run(request, run_id):
    """إعادة بناء مسير DRAFT."""
    if request.method != 'POST':
        return redirect('web:view_payroll_run', run_id=run_id)
    run = get_object_or_404(PayrollRun, id=run_id)
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()
    try:
        build_payroll_run(run.branch, run.period_year, run.period_month, request.user)
        messages.success(request, 'تم إعادة بناء المسير.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('web:view_payroll_run', run_id=run.id)


@login_required
@permission_required('employees.edit')
def lock_payroll_run_view(request, run_id):
    """ترحيل المسير."""
    if request.method != 'POST':
        return redirect('web:view_payroll_run', run_id=run_id)
    run = get_object_or_404(PayrollRun, id=run_id)
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()
    try:
        lock_payroll_run(run, request.user)
        messages.success(request, 'تم ترحيل المسير وتحديث جميع البنود.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('web:view_payroll_run', run_id=run.id)


@login_required
@permission_required('employees.edit')
def unlock_payroll_run_view(request, run_id):
    """إعادة فتح المسير (سوبر يوزر فقط)."""
    if request.method != 'POST':
        return redirect('web:view_payroll_run', run_id=run_id)
    if not request.user.is_superuser:
        messages.error(request, 'صلاحية إعادة فتح المسير للسوبر يوزر فقط.')
        return redirect('web:view_payroll_run', run_id=run_id)
    run = get_object_or_404(PayrollRun, id=run_id)
    try:
        unlock_payroll_run(run, request.user)
        messages.success(request, 'تم إعادة فتح المسير.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('web:view_payroll_run', run_id=run.id)


@login_required
@permission_required('employees.view')
def export_payroll_run_excel(request, run_id):
    """تصدير المسير إلى Excel."""
    try:
        from openpyxl import Workbook
    except ImportError:
        messages.error(request, 'مكتبة openpyxl غير مثبتة.')
        return redirect('web:view_payroll_run', run_id=run_id)

    run = get_object_or_404(PayrollRun.objects.select_related('branch'), id=run_id)
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()

    wb = Workbook()
    ws = wb.active
    ws.title = 'مسير الرواتب'
    ws.sheet_view.rightToLeft = True

    headers = [
        'الموظف', 'الأساسي', 'سكن', 'نقل', 'إضافي', 'كاش', 'الإجمالي',
        'مكافأة', 'ساعات إضافية',
        'أيام غياب', 'خصم غياب', 'أيام إجازة بدون راتب', 'خصم إجازة',
        'قسط سلفة', 'مخالفات', 'تأمينات', 'خصومات أخرى',
        'إجمالي الاستحقاقات', 'إجمالي الخصومات', 'الصافي'
    ]
    ws.append(headers)
    for line in run.lines.select_related('employee').order_by('employee__name'):
        ws.append([
            line.employee.name,
            float(line.basic_salary), float(line.housing_allowance),
            float(line.transport_allowance), float(line.other_allowance),
            float(line.cash_amount), float(line.gross_salary),
            float(line.bonus), float(line.overtime),
            float(line.absence_days), float(line.absence_deduction),
            float(line.unpaid_leave_days), float(line.unpaid_leave_deduction),
            float(line.loan_deduction), float(line.penalty_deduction),
            float(line.insurance_deduction), float(line.other_deduction),
            float(line.total_earnings), float(line.total_deductions),
            float(line.net_salary),
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    fname = f'payroll_{run.branch.id}_{run.period_year}_{run.period_month:02d}.xlsx'
    response['Content-Disposition'] = f'attachment; filename={fname}'
    wb.save(response)
    return response
