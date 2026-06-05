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
  - عرض: payroll.view
  - إنشاء/تعديل/ترحيل: payroll.manage أو payroll.process
  - إلغاء ترحيل: payroll.manage + superuser فقط
"""
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse, Http404
from django.db.models import Sum, Count

from apps.core.decorators import any_permission_required, permission_required
from apps.core.salary_access import user_can_manage_payroll
from apps.core.filter_utils import append_multi_param, parse_multi_filter_ids
from urllib.parse import urlencode
from apps.core.models import Branch
from apps.payroll.models import PayrollRun, PayrollLine


class _PayrollFilterOption:
    """خيار فلتر (قيمة نصية) — نفس شكل كائنات الفروع لقالب multiselect."""

    __slots__ = ('pk', 'name', 'code')

    def __init__(self, pk: str, name: str):
        self.pk = pk
        self.name = name
        self.code = ''


SALARY_MODE_FILTER_ITEMS = [
    _PayrollFilterOption(v, lbl) for v, lbl in PayrollRun.SalaryMode.choices
]
from apps.setup.models import Sponsorship
from apps.payroll.services.engine import (
    build_payroll_run, lock_payroll_run, unlock_payroll_run,
)
from apps.payroll.services.transfer_payroll import build_detailed_runs_for_branches


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


def _payroll_list_querystring(
    *,
    branch_ids=None,
    year=None,
    month=None,
    salary_mode=None,
    sponsorship_id=None,
    page=None,
):
    """سلسلة استعلام لشاشة المسير الموحّدة."""
    pairs: list[tuple[str, object]] = []
    append_multi_param(pairs, 'branch_id', branch_ids)
    if year:
        pairs.append(('year', year))
    if month:
        pairs.append(('month', month))
    if salary_mode:
        pairs.append(('salary_mode', salary_mode))
    if sponsorship_id:
        pairs.append(('sponsorship_id', sponsorship_id))
    if page:
        pairs.append(('page', page))
    return urlencode(pairs, doseq=True) if pairs else ''


def _parse_payroll_form(request, user_branches):
    """قراءة معايير المسير من GET أو POST."""
    accessible = None if request.user.is_superuser else list(user_branches.values_list('id', flat=True))
    use_post = request.method == 'POST'
    branch_ids = parse_multi_filter_ids(
        request, 'branch_id', accessible_ids=accessible,
    )
    if not branch_ids and not use_post:
        branch_ids = parse_multi_filter_ids(
            request, 'branch', accessible_ids=accessible,
        )
    branch_ids = branch_ids or []

    src = request.POST if use_post else request.GET
    year_raw = src.get('year')
    month_raw = src.get('month')
    salary_mode = ''
    mode_raw = list(src.getlist('salary_mode'))
    if not mode_raw:
        one = (src.get('salary_mode') or '').strip()
        if one:
            mode_raw = [one]
    for v in mode_raw:
        s = (str(v) or '').strip()
        if s in PayrollRun.SalaryMode.values:
            salary_mode = s
            break
    sponsorship_raw = (src.get('sponsorship_id') or '').strip()

    year = month = None
    try:
        if year_raw:
            year = int(year_raw)
        if month_raw:
            month = int(month_raw)
    except ValueError:
        pass

    sponsorship_id = None
    if sponsorship_raw.isdigit():
        sponsorship_id = int(sponsorship_raw)

    ready = bool(
        branch_ids and year and month
        and salary_mode in PayrollRun.SalaryMode.values
    )
    if ready and salary_mode == PayrollRun.SalaryMode.TRANSFER:
        ready = bool(sponsorship_id)

    return {
        'branch_ids': branch_ids,
        'year': year,
        'month': month,
        'salary_mode': salary_mode,
        'sponsorship_id': sponsorship_id,
        'ready': ready,
    }


def _validate_payroll_build(filters):
    """التحقق من صحة معايير البناء. يُرجع رسالة خطأ أو None."""
    if not filters['branch_ids']:
        return 'يرجى اختيار فرع واحد على الأقل.'
    y, m = filters['year'], filters['month']
    if not y or not m or not (2020 <= y <= 2100 and 1 <= m <= 12):
        return 'يرجى تحديد السنة والشهر.'
    if filters['salary_mode'] not in PayrollRun.SalaryMode.values:
        return 'يرجى اختيار نوع الراتب (نقدي أو تحويل).'
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        sid = filters['sponsorship_id']
        if not sid:
            return 'يرجى اختيار شركة الكفالة لمسير التحويل.'
        if not Sponsorship.objects.filter(
            pk=sid, is_deleted=False, is_active=True,
        ).exists():
            return 'شركة الكفالة غير صالحة.'
    return None


def _build_payroll_runs(request, filters):
    """بناء مسير لكل فرع. يُرجع (runs_built, errors)."""
    from django.db import transaction

    branch_ids = list(dict.fromkeys(filters['branch_ids']))
    branches = list(Branch.objects.filter(id__in=branch_ids, is_active=True).order_by('name'))
    if len(branches) != len(branch_ids):
        return [], ['أحد الفروع المختارة غير صالح أو غير متاح لحسابك.']

    sponsorship_id = (
        filters['sponsorship_id']
        if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER
        else None
    )
    runs_built = []
    errors = []
    try:
        with transaction.atomic():
            for branch in branches:
                try:
                    runs_built.append(
                        build_payroll_run(
                            branch, filters['year'], filters['month'], request.user,
                            salary_mode=filters['salary_mode'],
                            sponsorship_id=sponsorship_id,
                        )
                    )
                except ValueError as e:
                    errors.append(f'{branch.name}: {e}')
                    raise
    except ValueError:
        return [], errors
    return runs_built, errors


def _payroll_runs_for_filters(filters, user, user_branches):
    """مسيرات عادية مطابقة للمعايير."""
    qs = PayrollRun.objects.filter(
        branch_id__in=filters['branch_ids'],
        period_year=filters['year'],
        period_month=filters['month'],
        salary_mode=filters['salary_mode'],
        run_kind=PayrollRun.RunKind.STANDARD,
    ).select_related('branch', 'sponsorship')
    if not user.is_superuser:
        qs = qs.filter(branch__in=user_branches)
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        qs = qs.filter(sponsorship_id=filters['sponsorship_id'])
    else:
        qs = qs.filter(sponsorship__isnull=True)
    return qs.order_by('branch__name')


def _detailed_runs_for_filters(filters, user, user_branches):
    """مسيرات تفصيلية (نقل) للشركات المرتبطة بالفروع المختارة."""
    company_ids = Branch.objects.filter(
        id__in=filters['branch_ids'],
    ).values_list('company_id', flat=True).distinct()
    qs = PayrollRun.objects.filter(
        company_id__in=company_ids,
        period_year=filters['year'],
        period_month=filters['month'],
        salary_mode=filters['salary_mode'],
        run_kind=PayrollRun.RunKind.DETAILED,
    ).select_related('company', 'sponsorship')
    if not user.is_superuser:
        allowed = user_branches.values_list('company_id', flat=True).distinct()
        qs = qs.filter(company_id__in=allowed)
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        qs = qs.filter(sponsorship_id=filters['sponsorship_id'])
    else:
        qs = qs.filter(sponsorship__isnull=True)
    return qs.order_by('company__name')


def _build_detailed_payroll_runs(request, filters):
    from django.db import transaction

    branch_ids = list(dict.fromkeys(filters['branch_ids']))
    branches = list(Branch.objects.filter(id__in=branch_ids, is_active=True).order_by('name'))
    if len(branches) != len(branch_ids):
        return [], ['أحد الفروع المختارة غير صالح أو غير متاح لحسابك.']

    sponsorship_id = (
        filters['sponsorship_id']
        if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER
        else None
    )
    runs_built = []
    errors = []
    try:
        with transaction.atomic():
            runs_built = build_detailed_runs_for_branches(
                branches,
                filters['year'],
                filters['month'],
                request.user,
                salary_mode=filters['salary_mode'],
                sponsorship_id=sponsorship_id,
            )
    except ValueError as e:
        errors.append(str(e))
    return runs_built, errors


# ══════════════════════════════════════════════════════════════════════════════
# 1. شاشة المسير الموحّدة — بناء + جدول واحد لكل الفروع
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('payroll.view')
def list_payroll_runs(request):
    """بناء مسيرات لعدة فروع وعرض كل أسطر الموظفين في جدول واحد."""
    user_branches = _user_branches(request.user)
    filters = _parse_payroll_form(request, user_branches)

    if request.method == 'POST':
        if not user_can_manage_payroll(request.user):
            messages.error(request, 'ليس لديك صلاحية بناء المسير.')
        else:
            err = _validate_payroll_build(filters)
            if err:
                messages.error(request, err)
            else:
                build_detailed = request.POST.get('build_kind') == 'detailed'
                if build_detailed:
                    runs_built, build_errors = _build_detailed_payroll_runs(request, filters)
                    for e in build_errors:
                        messages.error(request, e)
                    if runs_built:
                        total_rows = sum(r.employees_count for r in runs_built)
                        messages.success(
                            request,
                            f'تم بناء {len(runs_built)} مسير تفصيلي '
                            f'({total_rows} موظف منقول).',
                        )
                else:
                    runs_built, build_errors = _build_payroll_runs(request, filters)
                    for e in build_errors:
                        messages.error(request, e)
                    if runs_built:
                        mode_label = dict(PayrollRun.SalaryMode.choices).get(
                            filters['salary_mode'], filters['salary_mode'],
                        )
                        total_emp = sum(r.employees_count for r in runs_built)
                        messages.success(
                            request,
                            f'تم بناء {len(runs_built)} مسير {mode_label} '
                            f'({total_emp} موظف في الجدول أدناه).',
                        )
        qs = _payroll_list_querystring(
            branch_ids=filters['branch_ids'],
            year=filters['year'],
            month=filters['month'],
            salary_mode=filters['salary_mode'] or None,
            sponsorship_id=filters['sponsorship_id'],
        )
        url = reverse('web:list_payroll_runs')
        return redirect(f'{url}?{qs}' if qs else url)

    lines = []
    page_obj = None
    grand_totals = {}
    runs_count = 0
    allocation_lines = []
    allocation_page_obj = None
    detailed_runs = []

    if filters['ready']:
        runs_qs = _payroll_runs_for_filters(filters, request.user, user_branches)
        runs_count = runs_qs.count()
        lines_qs = PayrollLine.objects.filter(run__in=runs_qs).select_related(
            'employee', 'run', 'run__branch',
        ).order_by('run__branch__name', 'employee__name')

        grand_totals = runs_qs.aggregate(
            total_earnings=Sum('total_earnings'),
            total_deductions=Sum('total_deductions'),
            total_net=Sum('total_net'),
            employees_count=Sum('employees_count'),
        )

        from django.core.paginator import Paginator
        paginator = Paginator(lines_qs, 50)
        page_obj = paginator.get_page(request.GET.get('page') or 1)
        lines = page_obj.object_list

        detailed_runs = list(_detailed_runs_for_filters(filters, request.user, user_branches))
        if detailed_runs:
            from apps.payroll.models import PayrollAllocationLine
            alloc_qs = PayrollAllocationLine.objects.filter(
                run__in=detailed_runs,
            ).select_related(
                'employee', 'branch', 'from_branch', 'run', 'run__company',
            ).order_by('employee__name', 'branch__name')
            from django.core.paginator import Paginator
            alloc_paginator = Paginator(alloc_qs, 50)
            allocation_page_obj = alloc_paginator.get_page(
                request.GET.get('alloc_page') or 1,
            )
            allocation_lines = allocation_page_obj.object_list

    today = date.today()
    sponsorships = Sponsorship.objects.filter(is_deleted=False, is_active=True).order_by('company_name')
    filter_qs = _payroll_list_querystring(
        branch_ids=filters['branch_ids'] if filters['ready'] else None,
        year=filters['year'],
        month=filters['month'],
        salary_mode=filters['salary_mode'] or None,
        sponsorship_id=filters['sponsorship_id'],
    )

    return render(request, 'pages/payroll/list.html', {
        'branches': user_branches,
        'sponsorships': sponsorships,
        'SALARY_MODE_CHOICES': PayrollRun.SalaryMode.choices,
        'current_year': today.year,
        'current_month': today.month,
        'years_range': range(today.year - 2, today.year + 1),
        'months_range': range(1, 13),
        'filter_branch_ids': filters['branch_ids'],
        'filter_year': filters['year'],
        'filter_month': filters['month'],
        'filter_salary_mode': filters['salary_mode'],
        'filter_salary_mode_ids': [filters['salary_mode']] if filters.get('salary_mode') else [],
        'salary_mode_filter_items': SALARY_MODE_FILTER_ITEMS,
        'filter_sponsorship_id': filters['sponsorship_id'],
        'filter_qs': filter_qs,
        'lines': lines,
        'page_obj': page_obj,
        'grand_totals': grand_totals,
        'runs_count': runs_count,
        'show_table': filters['ready'],
        'can_build': user_can_manage_payroll(request.user),
        'detailed_runs': detailed_runs,
        'allocation_lines': allocation_lines,
        'allocation_page_obj': allocation_page_obj,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 2. إنشاء/بناء مسير — يُوجّه للشاشة الموحّدة (توافق قديم)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@any_permission_required('payroll.manage', 'payroll.process')
def create_payroll_run(request):
    """توافق مع الرابط القديم — نفس شاشة القائمة الموحّدة."""
    if request.method == 'POST':
        return list_payroll_runs(request)
    return redirect('web:list_payroll_runs')


# ══════════════════════════════════════════════════════════════════════════════
# 3. عرض تفاصيل مسير — أسطر الموظفين مع كل البنود
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('payroll.view')
def view_payroll_run(request, run_id):
    """عرض تفاصيل المسير وأسطر الموظفين."""
    run = get_object_or_404(
        PayrollRun.objects.select_related(
            'branch', 'sponsorship', 'created_by', 'locked_by', 'company',
        ),
        id=run_id,
    )
    user_branches = _user_branches(request.user)
    if run.run_kind == PayrollRun.RunKind.DETAILED:
        if not request.user.is_superuser:
            allowed = user_branches.values_list('company_id', flat=True).distinct()
            if run.company_id not in allowed:
                raise Http404()
        from django.core.paginator import Paginator
        from apps.core.utils.pagination import clamp_page_size
        from apps.payroll.models import PayrollAllocationLine

        alloc_qs = run.allocation_lines.select_related(
            'employee', 'branch', 'from_branch',
        ).order_by('employee__name', 'branch__name')
        paginator = Paginator(
            alloc_qs,
            per_page=clamp_page_size(request.GET.get('per_page'), default=50, maximum=200),
        )
        page_obj = paginator.get_page(request.GET.get('page') or 1)
        return render(request, 'pages/payroll/view_detailed.html', {
            'run': run,
            'allocation_lines': page_obj.object_list,
            'page_obj': page_obj,
            'lines_total': paginator.count,
        })

    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()

    from django.core.paginator import Paginator
    from apps.core.utils.pagination import clamp_page_size

    lines_qs = run.lines.select_related('employee', 'employee__branch').order_by('employee__name')
    paginator = Paginator(
        lines_qs,
        per_page=clamp_page_size(request.GET.get('per_page'), default=50, maximum=200),
    )
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    return render(request, 'pages/payroll/view.html', {
        'run': run,
        'lines': page_obj.object_list,
        'page_obj': page_obj,
        'lines_total': paginator.count,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 4. إعادة بناء مسير DRAFT — يُحدّث الأرقام بالبيانات الحالية
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@any_permission_required('payroll.manage', 'payroll.process')
def rebuild_payroll_run(request, run_id):
    """إعادة بناء مسير DRAFT — يمسح الأسطر القديمة ويعيد حسابها."""
    if request.method != 'POST':
        return redirect('web:view_payroll_run', run_id=run_id)

    run = get_object_or_404(PayrollRun, id=run_id)
    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()
    try:
        if run.run_kind == PayrollRun.RunKind.DETAILED:
            from apps.payroll.services.transfer_payroll import build_payroll_detailed_run
            build_payroll_detailed_run(
                run.company, run.period_year, run.period_month, request.user,
                salary_mode=run.salary_mode,
                sponsorship_id=run.sponsorship_id,
            )
        else:
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
@any_permission_required('payroll.manage', 'payroll.process')
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
@any_permission_required('payroll.manage', 'payroll.process')
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
@permission_required('payroll.view')
def export_payroll_run_excel(request, run_id):
    """تصدير المسير إلى Excel ملوّن (.xlsx)."""
    try:
        from apps.payroll.services.export_excel import (
            build_payroll_run_workbook,
            payroll_run_excel_filename,
            workbook_to_response,
        )
    except ImportError:
        messages.error(request, 'مكتبة openpyxl غير مثبتة.')
        return redirect('web:view_payroll_run', run_id=run_id)

    run = get_object_or_404(
        PayrollRun.objects.select_related('branch', 'sponsorship'),
        id=run_id,
    )

    user_branches = _user_branches(request.user)
    if not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()

    wb = build_payroll_run_workbook(run)
    return workbook_to_response(wb, payroll_run_excel_filename(run))
