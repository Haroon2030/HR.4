"""
واجهات مسير الرواتب الشهري — Payroll Views
============================================
هذا الملف يحتوي على كل شاشات إدارة مسير الرواتب:

  1. list_payroll_runs   — قائمة المسيرات (مع فلاتر + ترقيم صفحات)
  2. create_payroll_run  — إنشاء/بناء مسير جديد لفرع وشهر
  3. view_payroll_run    — عرض تفاصيل مسير (أسطر الموظفين)
  4. rebuild_payroll_run — إعادة بناء مسير DRAFT (يحدّث الأرقام)
  5. lock_payroll_run    — ترحيل المسير (ربط البنود وتأكيدها)
  6. unlock_payroll_run  — إلغاء الترحيل (سوبر يوزر فقط)
  7. export_payroll_run  — تصدير المسير إلى Excel

دورة حياة المسير:
  DRAFT (مسودة) → بناء/إعادة بناء → LOCKED (مُرحَّل) → تصدير Excel
  LOCKED → unlock (سوبر يوزر فقط) → DRAFT مرة أخرى

الصلاحيات:
  - عرض: employees.view
  - إنشاء/تعديل/ترحيل: employees.edit
  - إلغاء ترحيل: employees.edit + superuser فقط
"""
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse, Http404
from django.db.models import Sum, Count

from apps.core.decorators import permission_required
from apps.core.filter_utils import append_multi_param, parse_multi_filter_ids
from urllib.parse import urlencode
from apps.core.models import Branch
from apps.payroll.models import PayrollRun, PayrollLine
from apps.setup.models import Sponsorship
from apps.payroll.services.engine import (
    build_payroll_run, lock_payroll_run, unlock_payroll_run,
)


def _user_branches(user):
    """
    جلب الفروع المتاحة للمستخدم.
    
    القواعد:
      - superuser / admin / hr_manager → كل الفروع النشطة
      - غيرهم → فرعه الشخصي + الفروع التي يديرها + المُسندة إليه
    """
    from apps.core.models import Role
    if user.is_superuser:
        return Branch.objects.filter(is_active=True).order_by('name')

    profile = getattr(user, 'profile', None)
    # الأدمن ومدير الموارد يرون كل الفروع
    if profile and profile.role and profile.role.role_type in (
        Role.RoleType.ADMIN, Role.RoleType.HR_MANAGER,
    ):
        return Branch.objects.filter(is_active=True).order_by('name')

    # باقي المستخدمين: تجميع فروعهم المتاحة
    from django.db.models import Q
    branch_ids = set()
    if profile:
        if profile.branch_id:
            branch_ids.add(profile.branch_id)           # فرعه الشخصي
        branch_ids.update(profile.assigned_branches.values_list('id', flat=True))  # المُعيّنة
    branch_ids.update(user.managed_branches.values_list('id', flat=True))           # التي يديرها

    if branch_ids:
        return Branch.objects.filter(id__in=branch_ids, is_active=True).order_by('name')
    return Branch.objects.none()


def _redirect_payroll_list(request, *, branch_ids=None, year=None, month=None, status=None):
    url = reverse('web:list_payroll_runs')
    qs = _payroll_list_querystring(
        branch_ids=branch_ids,
        year=year,
        month=month,
        status=status,
    )
    if qs:
        url = f'{url}?{qs}'
    return redirect(url)


def _payroll_list_querystring(*, branch_ids=None, year=None, month=None, status=None, page=None):
    """سلسلة استعلام لفلترة قائمة المسيرات (فروع متعددة)."""
    pairs: list[tuple[str, object]] = []
    append_multi_param(pairs, 'branch', branch_ids)
    if year:
        pairs.append(('year', year))
    if month:
        pairs.append(('month', month))
    if status:
        pairs.append(('status', status))
    if page:
        pairs.append(('page', page))
    return urlencode(pairs, doseq=True) if pairs else ''


# ══════════════════════════════════════════════════════════════════════════════
# 1. قائمة المسيرات — مع فلاتر (سنة/شهر/فرع/حالة) + ترقيم صفحات
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('employees.view')
def list_payroll_runs(request):
    """عرض قائمة مسيرات الرواتب مع إمكانية الفلترة والترقيم."""
    qs = PayrollRun.objects.select_related(
        'branch', 'company', 'sponsorship', 'created_by', 'locked_by',
    )
    user_branches = _user_branches(request.user)

    # تقييد بالفروع المتاحة للمستخدم
    if not request.user.is_superuser:
        qs = qs.filter(branch__in=user_branches)

    # ── تطبيق الفلاتر من معاملات URL ──
    year = request.GET.get('year')
    month = request.GET.get('month')
    status = request.GET.get('status')
    accessible = None if request.user.is_superuser else list(user_branches.values_list('id', flat=True))
    branch_ids = parse_multi_filter_ids(request, 'branch', accessible_ids=accessible)
    if year:
        qs = qs.filter(period_year=year)
    if month:
        qs = qs.filter(period_month=month)
    if branch_ids:
        qs = qs.filter(branch_id__in=branch_ids)
    if status:
        qs = qs.filter(status=status)

    # ── ترقيم الصفحات — 20 مسير في كل صفحة ──
    from django.core.paginator import Paginator
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    today = date.today()
    sponsorships = Sponsorship.objects.filter(is_deleted=False, is_active=True).order_by('company_name')
    filter_qs = _payroll_list_querystring(
        branch_ids=branch_ids,
        year=year,
        month=month,
        status=status,
    )
    return render(request, 'pages/payroll/list.html', {
        'runs': page_obj.object_list,        # المسيرات في الصفحة الحالية
        'page_obj': page_obj,                # كائن الصفحة (للترقيم)
        'paginator': paginator,              # كائن الترقيم
        'branches': user_branches,           # الفروع (للقائمة المنسدلة)
        'sponsorships': sponsorships,
        'SALARY_MODE_CHOICES': PayrollRun.SalaryMode.choices,
        'current_year': today.year,
        'current_month': today.month,
        'years_range': range(today.year - 2, today.year + 1),
        'months_range': range(1, 13),
        'filter_year': year, 'filter_month': month,
        'filter_branch_ids': branch_ids or [],
        'filter_status': status,
        'filter_qs': filter_qs,
        'STATUS_CHOICES': PayrollRun.Status.choices,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 2. إنشاء/بناء مسير — POST فقط
# يبني مسير DRAFT جديد أو يُحدّث الموجود (إذا لم يكن مُغلقاً)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('employees.edit')
def create_payroll_run(request):
    """إنشاء أو إعادة بناء مسير لشهر وفروع محددة (واحد أو أكثر)."""
    if request.method != 'POST':
        return redirect('web:list_payroll_runs')

    def _back(**kwargs):
        return _redirect_payroll_list(
            request,
            branch_ids=kwargs.get('branch_ids'),
            year=kwargs.get('year') or request.POST.get('year'),
            month=kwargs.get('month') or request.POST.get('month'),
        )

    try:
        year = int(request.POST.get('year') or 0)
        month = int(request.POST.get('month') or 0)
    except ValueError:
        messages.error(request, 'بيانات غير صحيحة.')
        return _back()

    if not (2020 <= year <= 2100 and 1 <= month <= 12):
        messages.error(request, 'يرجى تحديد السنة والشهر.')
        return _back(year=str(year), month=str(month))

    salary_mode = (request.POST.get('salary_mode') or '').strip()
    if salary_mode not in PayrollRun.SalaryMode.values:
        messages.error(request, 'يرجى اختيار نوع الراتب (نقدي أو تحويل).')
        return _back(year=str(year), month=str(month))

    user_branches = _user_branches(request.user)
    accessible = None if request.user.is_superuser else list(user_branches.values_list('id', flat=True))
    branch_ids = parse_multi_filter_ids(request, 'branch_id', accessible_ids=accessible) or []
    if not branch_ids:
        messages.error(request, 'يرجى اختيار فرع واحد على الأقل.')
        return _back(year=str(year), month=str(month))

    def _back_with_branches():
        return _back(branch_ids=branch_ids, year=str(year), month=str(month))

    try:
        sponsorship_id = int(request.POST.get('sponsorship_id') or 0)
    except ValueError:
        sponsorship_id = 0
    if salary_mode == PayrollRun.SalaryMode.TRANSFER:
        if not sponsorship_id:
            messages.error(request, 'يرجى اختيار شركة الكفالة لمسير التحويل.')
            return _back_with_branches()
        if not Sponsorship.objects.filter(
            pk=sponsorship_id, is_deleted=False, is_active=True,
        ).exists():
            messages.error(request, 'شركة الكفالة غير صالحة.')
            return _back_with_branches()
    else:
        sponsorship_id = None

    branches = list(Branch.objects.filter(id__in=branch_ids, is_active=True).order_by('name'))
    if len(branches) != len(branch_ids):
        messages.error(request, 'أحد الفروع المختارة غير صالح.')
        return _back_with_branches()

    mode_label = dict(PayrollRun.SalaryMode.choices).get(salary_mode, salary_mode)
    runs_built = []
    errors = []

    for branch in branches:
        try:
            run = build_payroll_run(
                branch, year, month, request.user,
                salary_mode=salary_mode,
                sponsorship_id=sponsorship_id or None,
            )
            runs_built.append(run)
        except ValueError as e:
            errors.append(f'{branch.name}: {e}')

    for err in errors:
        messages.error(request, err)

    if not runs_built:
        return _back_with_branches()

    total_employees = sum(r.employees_count for r in runs_built)
    if len(runs_built) == 1:
        run = runs_built[0]
        messages.success(
            request,
            f'تم بناء مسير {mode_label} لـ {run.branch.name} — {run.period_label} ({run.employees_count} موظف).',
        )
        return redirect('web:view_payroll_run', run_id=run.id)

    names = '، '.join(r.branch.name for r in runs_built[:5])
    if len(runs_built) > 5:
        names += f' و{len(runs_built) - 5} آخرين'
    messages.success(
        request,
        f'تم بناء {len(runs_built)} مسير {mode_label} — {names} ({total_employees} موظف إجمالاً).',
    )
    qs = _payroll_list_querystring(
        branch_ids=[r.branch_id for r in runs_built],
        year=str(year),
        month=str(month),
    )
    url = reverse('web:list_payroll_runs')
    if qs:
        url = f'{url}?{qs}'
    return redirect(url)


# ══════════════════════════════════════════════════════════════════════════════
# 3. عرض تفاصيل مسير — أسطر الموظفين مع كل البنود
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('employees.view')
def view_payroll_run(request, run_id):
    """عرض تفاصيل المسير وأسطر الموظفين."""
    run = get_object_or_404(
        PayrollRun.objects.select_related('branch', 'sponsorship', 'created_by', 'locked_by'),
        id=run_id
    )
    # فحص صلاحية الفرع
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()

    lines = run.lines.select_related('employee').order_by('employee__name')
    return render(request, 'pages/payroll/view.html', {
        'run': run,
        'lines': lines,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 4. إعادة بناء مسير DRAFT — يُحدّث الأرقام بالبيانات الحالية
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('employees.edit')
def rebuild_payroll_run(request, run_id):
    """إعادة بناء مسير DRAFT — يمسح الأسطر القديمة ويعيد حسابها."""
    if request.method != 'POST':
        return redirect('web:view_payroll_run', run_id=run_id)

    run = get_object_or_404(PayrollRun, id=run_id)
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()
    try:
        build_payroll_run(
            run.branch, run.period_year, run.period_month, request.user,
            salary_mode=run.salary_mode,
            sponsorship_id=run.sponsorship_id,
        )
        messages.success(request, 'تم إعادة بناء المسير.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('web:view_payroll_run', run_id=run.id)


# ══════════════════════════════════════════════════════════════════════════════
# 5. ترحيل المسير (قفل) — يربط كل بنود الخصم بالمسير ويمنع التعديل
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('employees.edit')
def lock_payroll_run_view(request, run_id):
    """ترحيل المسير — يُغلق التعديل ويربط بنود الخصم."""
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


# ══════════════════════════════════════════════════════════════════════════════
# 6. إلغاء الترحيل — سوبر يوزر فقط!
# يفك ربط كل بنود الخصم ويعيد المسير لحالة DRAFT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('employees.edit')
def unlock_payroll_run_view(request, run_id):
    """
    إعادة فتح مسير مُرحَّل — سوبر يوزر فقط!
    
    ⚠️ تحذير: هذا يفك ربط كل بنود الخصم (غياب، سلف، مخالفات)
    ويعيدها لحالة "غير مُحتسبة" — يجب إعادة بناء المسير بعدها.
    """
    if request.method != 'POST':
        return redirect('web:view_payroll_run', run_id=run_id)

    # فحص مزدوج: decorator + فحص داخلي
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


# ══════════════════════════════════════════════════════════════════════════════
# 7. تصدير المسير إلى Excel — ملف .xlsx قابل للتنزيل
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('employees.view')
def export_payroll_run_excel(request, run_id):
    """
    تصدير المسير إلى ملف Excel (.xlsx).
    يتطلب مكتبة openpyxl.
    
    أعمدة الملف:
      الموظف | الراتب الأساسي | البدلات | الإجمالي | الخصومات | الصافي
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        messages.error(request, 'مكتبة openpyxl غير مثبتة.')
        return redirect('web:view_payroll_run', run_id=run_id)

    run = get_object_or_404(PayrollRun.objects.select_related('branch'), id=run_id)

    # فحص صلاحية الفرع
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()

    # إنشاء ملف Excel
    wb = Workbook()
    ws = wb.active
    ws.title = 'مسير الرواتب'
    ws.sheet_view.rightToLeft = True  # دعم RTL للعربية

    # ── رؤوس الأعمدة ──
    headers = [
        'الموظف', 'الأساسي', 'سكن', 'نقل', 'إضافي', 'كاش', 'تغذية', 'الإجمالي',
        'مكافأة', 'ساعات إضافية',
        'أيام غياب', 'خصم غياب', 'أيام إجازة بدون راتب', 'خصم إجازة',
        'قسط سلفة', 'مخالفات', 'تأمينات', 'خصومات أخرى',
        'إجمالي الاستحقاقات', 'إجمالي الخصومات', 'الصافي'
    ]
    ws.append(headers)

    # ── أسطر الموظفين ──
    for line in run.lines.select_related('employee').order_by('employee__name'):
        ws.append([
            line.employee.name,
            float(line.basic_salary), float(line.housing_allowance),
            float(line.transport_allowance), float(line.other_allowance),
            float(line.cash_amount), float(line.meal_allowance), float(line.gross_salary),
            float(line.bonus), float(line.overtime),
            float(line.absence_days), float(line.absence_deduction),
            float(line.unpaid_leave_days), float(line.unpaid_leave_deduction),
            float(line.loan_deduction), float(line.penalty_deduction),
            float(line.insurance_deduction), float(line.other_deduction),
            float(line.total_earnings), float(line.total_deductions),
            float(line.net_salary),
        ])

    # ── إرسال الملف كتنزيل ──
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    fname = f'payroll_{run.branch.id}_{run.period_year}_{run.period_month:02d}.xlsx'
    response['Content-Disposition'] = f'attachment; filename={fname}'
    wb.save(response)
    return response
