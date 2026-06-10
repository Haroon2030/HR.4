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
from django.db.models import Prefetch, Sum, Count

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

_PAYROLL_LIST_SESSION_KEY = 'hr_payroll_list_filters'

from apps.setup.models import Sponsorship
from apps.payroll.services.engine import (
    build_payroll_run,
    build_consolidated_payroll_run,
    lock_payroll_run,
    unlock_payroll_run,
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
    sponsorship_ids=None,
    page=None,
    open_run_id=None,
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
    append_multi_param(pairs, 'sponsorship_id', sponsorship_ids)
    if page:
        pairs.append(('page', page))
    if open_run_id:
        pairs.append(('open_run', open_run_id))
    return urlencode(pairs, doseq=True) if pairs else ''


def _parse_open_run_id(request) -> int | None:
    raw = (request.GET.get('open_run') or '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _active_sponsorship_ids() -> list[int]:
    return list(
        Sponsorship.objects.filter(is_deleted=False, is_active=True)
        .order_by('company_name')
        .values_list('id', flat=True),
    )


def _effective_sponsorship_ids(filters) -> list[int]:
    """قائمة شركات الكفالة للبناء/العرض. None في الفلتر = جميع الشركات."""
    if filters['salary_mode'] != PayrollRun.SalaryMode.TRANSFER:
        return []
    ids = filters.get('sponsorship_ids')
    if ids is None:
        return _active_sponsorship_ids()
    return list(ids)


def _resolved_branch_ids(filters, user_branches) -> list[int]:
    """فروع المسير — None في الفلتر = جميع الفروع المتاحة للمستخدم."""
    ids = filters.get('branch_ids')
    if ids:
        return list(dict.fromkeys(ids))
    return list(user_branches.values_list('id', flat=True))


def _default_payroll_period(filters: dict) -> dict:
    """توحيد السنة/الشهر مع القيم الافتراضية في الواجهة."""
    today = date.today()
    if not filters.get('year'):
        filters['year'] = today.year
    if not filters.get('month'):
        filters['month'] = today.month
    return filters


def _recompute_payroll_ready(filters: dict) -> dict:
    ready = bool(
        filters.get('year') and filters.get('month')
        and filters.get('salary_mode') in PayrollRun.SalaryMode.values
    )
    if ready and filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        ready = filters.get('sponsorship_ids') is None or bool(filters['sponsorship_ids'])
    filters['ready'] = ready
    return filters


def _store_payroll_list_filters(request, filters: dict) -> None:
    if not filters.get('ready'):
        return
    branch_ids = filters.get('branch_ids')
    request.session[_PAYROLL_LIST_SESSION_KEY] = {
        'branch_ids': list(branch_ids) if branch_ids else None,
        'year': filters['year'],
        'month': filters['month'],
        'salary_mode': filters['salary_mode'],
        'sponsorship_ids': filters['sponsorship_ids'],
    }
    request.session.modified = True


def _consolidated_runs_qs(filters: dict, user, user_branches, branch_ids):
    """مسيرات موحّدة لشركات الفروع المحددة."""
    company_ids = Branch.objects.filter(
        id__in=branch_ids,
    ).values_list('company_id', flat=True).distinct()
    qs = PayrollRun.objects.filter(
        run_kind=PayrollRun.RunKind.CONSOLIDATED,
        period_year=filters['year'],
        period_month=filters['month'],
        salary_mode=filters['salary_mode'],
        company_id__in=company_ids,
    ).select_related('company', 'sponsorship')
    if not user.is_superuser:
        allowed = user_branches.values_list('company_id', flat=True).distinct()
        qs = qs.filter(company_id__in=allowed)
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        sp_ids = filters.get('sponsorship_ids')
        if sp_ids is not None:
            qs = qs.filter(sponsorship_id__in=sp_ids)
    else:
        qs = qs.filter(sponsorship__isnull=True)
    return qs


def _prefer_consolidated_runs(filters: dict, branch_ids) -> bool:
    """مسودة واحدة عند عدم تحديد فرع أو عند اختيار أكثر من فرع."""
    return len(branch_ids) > 1 or not filters.get('branch_ids')


def _draft_runs_for_period(filters: dict, user, user_branches, *, branch_ids=None):
    """مسودات لشهر محدد (موحّدة أو STANDARD حسب الفلاتر)."""
    year, month = filters.get('year'), filters.get('month')
    if not year or not month:
        return []
    resolved = branch_ids or list(_resolved_branch_ids(filters, user_branches))
    if _prefer_consolidated_runs(filters, resolved):
        qs = PayrollRun.objects.filter(
            period_year=year,
            period_month=month,
            run_kind=PayrollRun.RunKind.CONSOLIDATED,
            status=PayrollRun.Status.DRAFT,
        )
        if not user.is_superuser:
            allowed = user_branches.values_list('company_id', flat=True).distinct()
            qs = qs.filter(company_id__in=allowed)
        return list(qs.select_related('company', 'sponsorship').order_by('-updated_at'))
    qs = PayrollRun.objects.filter(
        period_year=year,
        period_month=month,
        run_kind=PayrollRun.RunKind.STANDARD,
        status=PayrollRun.Status.DRAFT,
    )
    if not user.is_superuser:
        qs = qs.filter(branch__in=user_branches)
    if branch_ids:
        qs = qs.filter(branch_id__in=branch_ids)
    return list(qs.select_related('branch', 'sponsorship').order_by('-updated_at'))


def _period_payroll_runs(filters: dict, user, user_branches, salary_mode: str, *, branch_ids=None):
    """مسيرات الشهر ونوع الراتب — موحّدة أو حسب الفرع."""
    year, month = filters.get('year'), filters.get('month')
    if not year or not month or salary_mode not in PayrollRun.SalaryMode.values:
        return []
    resolved = branch_ids if branch_ids is not None else list(_resolved_branch_ids(filters, user_branches))
    line_prefetch = Prefetch(
        'lines',
        queryset=PayrollLine.objects.select_related('employee').order_by('employee__name'),
    )
    if _prefer_consolidated_runs(filters, resolved):
        mode_filters = dict(filters)
        mode_filters['salary_mode'] = salary_mode
        qs = _consolidated_runs_qs(mode_filters, user, user_branches, resolved)
        consolidated = list(
            qs.prefetch_related(line_prefetch)
            .order_by('status', 'sponsorship__company_name', 'id'),
        )
        if consolidated:
            return consolidated
    qs = PayrollRun.objects.filter(
        period_year=year,
        period_month=month,
        run_kind=PayrollRun.RunKind.STANDARD,
        salary_mode=salary_mode,
    ).select_related('branch', 'sponsorship')
    if not user.is_superuser:
        qs = qs.filter(branch__in=user_branches)
    if branch_ids:
        qs = qs.filter(branch_id__in=branch_ids)
    return list(
        qs.prefetch_related(line_prefetch)
        .order_by('status', 'branch__name', 'sponsorship__company_name', 'id'),
    )


def _payroll_mode_run_counts(filters: dict, user, user_branches, *, branch_ids=None) -> dict[str, int]:
    counts = {}
    for mode in PayrollRun.SalaryMode.values:
        counts[mode] = len(_period_payroll_runs(filters, user, user_branches, mode, branch_ids=branch_ids))
    return counts


def _period_run_totals(runs: list) -> dict:
    from decimal import Decimal
    return {
        'runs_count': len(runs),
        'employees_count': sum(int(r.employees_count or 0) for r in runs),
        'total_earnings': sum(Decimal(r.total_earnings or 0) for r in runs),
        'total_deductions': sum(Decimal(r.total_deductions or 0) for r in runs),
        'total_net': sum(Decimal(r.total_net or 0) for r in runs),
    }


def _runs_for_unified_export(filters: dict, user, user_branches):
    """كل مسيرات الشهر/النوع في ملف تصدير واحد — بغض النظر عن فلتر فرع العرض."""
    export_filters = dict(filters)
    export_filters['branch_ids'] = None
    return list(_payroll_runs_for_filters(export_filters, user, user_branches))


def _payroll_run_open_url(run: PayrollRun) -> str:
    pairs: list[tuple[str, object]] = [
        ('year', run.period_year),
        ('month', run.period_month),
        ('salary_mode', run.salary_mode),
        ('open_run', run.pk),
    ]
    if run.branch_id:
        pairs.append(('branch_id', run.branch_id))
    if run.sponsorship_id:
        pairs.append(('sponsorship_id', run.sponsorship_id))
    return f"{reverse('web:list_payroll_runs')}?{urlencode(pairs)}"


def _apply_draft_run_to_filters(filters: dict, run: PayrollRun) -> dict:
    if run.branch_id and not filters.get('branch_ids'):
        filters['branch_ids'] = [run.branch_id]
    if not filters.get('salary_mode'):
        filters['salary_mode'] = run.salary_mode
    if (
        run.salary_mode == PayrollRun.SalaryMode.TRANSFER
        and run.sponsorship_id
        and filters.get('sponsorship_ids') is None
    ):
        filters['sponsorship_ids'] = [run.sponsorship_id]
    return filters


def _infer_payroll_filters_from_drafts(filters: dict, user, user_branches) -> dict:
    """استنتاج الفروع/النوع/الكفالة من مسودات محفوظة لنفس الشهر."""
    if filters.get('salary_mode'):
        return filters

    year, month = filters.get('year'), filters.get('month')
    if not year or not month:
        return filters

    branch_ids = filters.get('branch_ids') or None
    runs = _draft_runs_for_period(filters, user, user_branches, branch_ids=branch_ids)
    if not runs:
        return filters

    if branch_ids:
        modes = {r.salary_mode for r in runs}
        if len(modes) == 1:
            filters['salary_mode'] = next(iter(modes))
            if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
                sp_ids = list(dict.fromkeys(
                    r.sponsorship_id for r in runs if r.sponsorship_id
                ))
                if len(sp_ids) == 1:
                    filters['sponsorship_ids'] = sp_ids
        elif len(modes) > 1:
            filters = _apply_draft_run_to_filters(filters, runs[0])
        return filters

    modes = {r.salary_mode for r in runs}
    if len(modes) != 1:
        return _apply_draft_run_to_filters(filters, runs[0])

    filters['branch_ids'] = list(dict.fromkeys(r.branch_id for r in runs if r.branch_id))
    filters['salary_mode'] = next(iter(modes))
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        sp_ids = list(dict.fromkeys(r.sponsorship_id for r in runs if r.sponsorship_id))
        filters['sponsorship_ids'] = sp_ids if len(sp_ids) == 1 else None
    return filters


def _merge_stored_payroll_filters(filters: dict, stored: dict) -> dict:
    if 'branch_ids' in stored and not filters.get('branch_ids'):
        stored_branches = stored['branch_ids']
        filters['branch_ids'] = list(stored_branches) if stored_branches else None
    if stored.get('salary_mode') and not filters.get('salary_mode'):
        filters['salary_mode'] = stored['salary_mode']
    if 'sponsorship_ids' in stored and filters.get('sponsorship_ids') is None:
        filters['sponsorship_ids'] = stored['sponsorship_ids']
    if stored.get('year'):
        filters['year'] = stored['year']
    if stored.get('month'):
        filters['month'] = stored['month']
    return filters


def _payroll_filters_missing_from_query(request, filters: dict) -> bool:
    """هل الرابط ناقص مع أن الفلاتر جاهزة للعرض؟"""
    if not filters.get('ready'):
        return False
    if filters.get('branch_ids') and not request.GET.getlist('branch_id'):
        return True
    if filters.get('salary_mode') and not (request.GET.get('salary_mode') or '').strip():
        return True
    if filters.get('sponsorship_ids') and not request.GET.getlist('sponsorship_id'):
        return True
    return False


def _restore_payroll_list_filters(request, filters: dict, user, user_branches):
    """استعادة آخر فلاتر أو مسودات محفوظة عند فتح الصفحة."""
    filters = _default_payroll_period(filters)
    if request.method != 'GET':
        return _recompute_payroll_ready(filters), None

    stored = request.session.get(_PAYROLL_LIST_SESSION_KEY)
    if stored:
        filters = _merge_stored_payroll_filters(filters, stored)

    filters = _infer_payroll_filters_from_drafts(filters, user, user_branches)
    if not filters.get('salary_mode'):
        filters['salary_mode'] = PayrollRun.SalaryMode.TRANSFER
    filters = _recompute_payroll_ready(filters)

    redirect_response = None
    if _payroll_filters_missing_from_query(request, filters):
        redirect_response = _redirect_payroll_list(request, filters)
    return filters, redirect_response


def _count_saved_draft_runs(filters: dict, user, user_branches) -> int:
    year, month = filters.get('year'), filters.get('month')
    if not year or not month:
        return 0
    branch_ids = list(_resolved_branch_ids(filters, user_branches))
    if _prefer_consolidated_runs(filters, branch_ids):
        qs = PayrollRun.objects.filter(
            period_year=year,
            period_month=month,
            run_kind=PayrollRun.RunKind.CONSOLIDATED,
            status=PayrollRun.Status.DRAFT,
        )
        if not user.is_superuser:
            allowed = user_branches.values_list('company_id', flat=True).distinct()
            qs = qs.filter(company_id__in=allowed)
        return qs.count()
    qs = PayrollRun.objects.filter(
        period_year=year,
        period_month=month,
        run_kind=PayrollRun.RunKind.STANDARD,
        status=PayrollRun.Status.DRAFT,
    )
    if not user.is_superuser:
        qs = qs.filter(branch__in=user_branches)
    if filters.get('branch_ids'):
        qs = qs.filter(branch_id__in=filters['branch_ids'])
    return qs.count()


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
    sponsorship_ids = parse_multi_filter_ids(request, 'sponsorship_id')

    year = month = None
    try:
        if year_raw:
            year = int(year_raw)
        if month_raw:
            month = int(month_raw)
    except ValueError:
        pass

    filters = {
        'branch_ids': branch_ids,
        'year': year,
        'month': month,
        'salary_mode': salary_mode,
        'sponsorship_ids': sponsorship_ids,
        'ready': False,
    }
    return _recompute_payroll_ready(_default_payroll_period(filters))


def _validate_payroll_build(filters, user_branches):
    """التحقق من صحة معايير البناء. يُرجع رسالة خطأ أو None."""
    if not _resolved_branch_ids(filters, user_branches):
        return 'لا توجد فروع متاحة لحسابك.'
    y, m = filters['year'], filters['month']
    if not y or not m or not (2020 <= y <= 2100 and 1 <= m <= 12):
        return 'يرجى تحديد السنة والشهر.'
    if filters['salary_mode'] not in PayrollRun.SalaryMode.values:
        return 'يرجى اختيار نوع الراتب (نقدي أو تحويل).'
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        effective = _effective_sponsorship_ids(filters)
        if not effective:
            return 'لا توجد شركات كفالة نشطة.'
        if filters['sponsorship_ids'] is not None:
            allowed = set(_active_sponsorship_ids())
            if not set(filters['sponsorship_ids']).issubset(allowed):
                return 'إحدى شركات الكفالة المختارة غير صالحة.'
    return None


def _build_payroll_runs(request, filters, user_branches):
    """بناء مسير موحّد (عدة فروع) أو مسير لكل فرع (فرع واحد)."""
    from django.db import transaction

    branch_ids = _resolved_branch_ids(filters, user_branches)
    branches = list(Branch.objects.filter(id__in=branch_ids, is_active=True).order_by('name'))
    if len(branches) != len(branch_ids):
        return [], ['أحد الفروع المختارة غير صالح أو غير متاح لحسابك.']

    sponsorship_ids = (
        _effective_sponsorship_ids(filters)
        if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER
        else [None]
    )
    runs_built = []
    errors = []
    use_consolidated = len(branches) > 1
    try:
        with transaction.atomic():
            for sponsorship_id in sponsorship_ids:
                if use_consolidated:
                    try:
                        runs_built.append(
                            build_consolidated_payroll_run(
                                branches, filters['year'], filters['month'], request.user,
                                salary_mode=filters['salary_mode'],
                                sponsorship_id=sponsorship_id,
                            )
                        )
                    except ValueError as e:
                        sp_label = f' / كفالة #{sponsorship_id}' if sponsorship_id else ''
                        errors.append(f'مسير موحّد{sp_label}: {e}')
                        raise
                else:
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
                            sp_label = f' / كفالة #{sponsorship_id}' if sponsorship_id else ''
                            errors.append(f'{branch.name}{sp_label}: {e}')
                            raise
    except ValueError:
        return [], errors
    return runs_built, errors


def _payroll_runs_for_filters(filters, user, user_branches):
    """مسيرات مطابقة للمعايير — موحّدة أو حسب الفرع."""
    branch_ids = list(_resolved_branch_ids(filters, user_branches))
    if _prefer_consolidated_runs(filters, branch_ids):
        qs = _consolidated_runs_qs(filters, user, user_branches, branch_ids)
        if qs.exists():
            return qs.order_by('sponsorship__company_name')
    qs = PayrollRun.objects.filter(
        branch_id__in=branch_ids,
        period_year=filters['year'],
        period_month=filters['month'],
        salary_mode=filters['salary_mode'],
        run_kind=PayrollRun.RunKind.STANDARD,
    ).select_related('branch', 'sponsorship')
    if not user.is_superuser:
        qs = qs.filter(branch__in=user_branches)
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        sp_ids = filters.get('sponsorship_ids')
        if sp_ids is not None:
            qs = qs.filter(sponsorship_id__in=sp_ids)
    else:
        qs = qs.filter(sponsorship__isnull=True)
    return qs.order_by('branch__name')


def _detailed_runs_for_filters(filters, user, user_branches):
    """مسيرات تفصيلية (نقل) للشركات المرتبطة بالفروع المختارة."""
    branch_ids = _resolved_branch_ids(filters, user_branches)
    company_ids = Branch.objects.filter(
        id__in=branch_ids,
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
        sp_ids = filters.get('sponsorship_ids')
        if sp_ids is not None:
            qs = qs.filter(sponsorship_id__in=sp_ids)
    else:
        qs = qs.filter(sponsorship__isnull=True)
    return qs.order_by('company__name')


def _build_detailed_payroll_runs(request, filters, user_branches):
    from django.db import transaction

    branch_ids = _resolved_branch_ids(filters, user_branches)
    branches = list(Branch.objects.filter(id__in=branch_ids, is_active=True).order_by('name'))
    if len(branches) != len(branch_ids):
        return [], ['أحد الفروع المختارة غير صالح أو غير متاح لحسابك.']

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
                sponsorship_ids=(
                    _effective_sponsorship_ids(filters)
                    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER
                    else None
                ),
            )
    except ValueError as e:
        errors.append(str(e))
    return runs_built, errors


def _lock_payroll_runs_for_filters(request, filters, user, user_branches):
    """ترحيل كل مسيرات STANDARD المطابقة للفلاتر. يُرجع (locked_count, errors)."""
    runs = list(_payroll_runs_for_filters(filters, user, user_branches))
    locked = 0
    errors = []
    skipped = 0
    for run in runs:
        if run.status == PayrollRun.Status.LOCKED:
            skipped += 1
            continue
        try:
            lock_payroll_run(run, user)
            locked += 1
        except ValueError as e:
            if run.branch_id:
                label = run.branch.name
            elif run.run_kind == PayrollRun.RunKind.CONSOLIDATED and run.company_id:
                label = f'{run.company.name} — موحّد'
            else:
                label = f'مسير #{run.pk}'
            errors.append(f'{label}: {e}')
    if skipped and not locked and not errors:
        errors.append('جميع المسيرات مُرحَّلة مسبقاً.')
    return locked, errors


def _redirect_payroll_list(request, filters, *, open_run_id=None):
    _store_payroll_list_filters(request, filters)
    qs = _payroll_list_querystring(
        branch_ids=filters['branch_ids'],
        year=filters['year'],
        month=filters['month'],
        salary_mode=filters['salary_mode'] or None,
        sponsorship_ids=filters['sponsorship_ids'],
        open_run_id=open_run_id,
    )
    url = reverse('web:list_payroll_runs')
    return redirect(f'{url}?{qs}' if qs else url)


# ══════════════════════════════════════════════════════════════════════════════
# 1. شاشة المسير الموحّدة — بناء + جدول واحد لكل الفروع
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('payroll.view')
def list_payroll_runs(request):
    """بناء مسيرات لعدة فروع وعرض كل أسطر الموظفين في جدول واحد."""
    user_branches = _user_branches(request.user)
    filters = _parse_payroll_form(request, user_branches)
    filters, redirect_response = _restore_payroll_list_filters(
        request, filters, request.user, user_branches,
    )
    if redirect_response is not None:
        return redirect_response

    if request.method == 'POST':
        payroll_action = (request.POST.get('payroll_action') or '').strip()
        build_kind = (request.POST.get('build_kind') or '').strip()

        if not user_can_manage_payroll(request.user):
            messages.error(request, 'ليس لديك صلاحية إدارة المسير.')
        else:
            err = _validate_payroll_build(filters, user_branches)
            if err:
                messages.error(request, err)
            elif payroll_action == 'lock':
                locked, lock_errors = _lock_payroll_runs_for_filters(
                    request, filters, request.user, user_branches,
                )
                for e in lock_errors:
                    messages.error(request, e)
                if locked:
                    messages.success(
                        request,
                        f'تم الإغلاق النهائي لـ {locked} مسير وربط بنود الخصم.',
                    )
            elif payroll_action == 'save' or build_kind == 'standard':
                runs_built, build_errors = _build_payroll_runs(request, filters, user_branches)
                for e in build_errors:
                    messages.error(request, e)
                if runs_built:
                    if payroll_action == 'save':
                        messages.success(
                            request,
                            f'تم حفظ المسير كمسودة ({sum(r.employees_count for r in runs_built)} موظف).',
                        )
                    else:
                        mode_label = dict(PayrollRun.SalaryMode.choices).get(
                            filters['salary_mode'], filters['salary_mode'],
                        )
                        total_emp = sum(r.employees_count for r in runs_built)
                        if any(r.run_kind == PayrollRun.RunKind.CONSOLIDATED for r in runs_built):
                            messages.success(
                                request,
                                f'تم بناء مسير موحّد {mode_label} '
                                f'({total_emp} موظف — ملف ومسودة واحدة لكل الفروع).',
                            )
                        else:
                            messages.success(
                                request,
                                f'تم بناء {len(runs_built)} مسير {mode_label} '
                                f'({total_emp} موظف — افتح الصف لعرض التفاصيل).',
                            )
                if runs_built:
                    return _redirect_payroll_list(
                        request, filters, open_run_id=runs_built[0].pk,
                    )
            elif build_kind == 'detailed':
                runs_built, build_errors = _build_detailed_payroll_runs(request, filters, user_branches)
                for e in build_errors:
                    messages.error(request, e)
                if runs_built:
                    total_rows = sum(r.employees_count for r in runs_built)
                    messages.success(
                        request,
                        f'تم بناء {len(runs_built)} مسير تفصيلي '
                        f'({total_rows} موظف منقول).',
                    )
        return _redirect_payroll_list(request, filters)

    if request.method == 'GET' and filters['ready']:
        _store_payroll_list_filters(request, filters)

    payroll_runs = []
    open_run_id = _parse_open_run_id(request)
    grand_totals = {}
    runs_count = 0
    has_draft_runs = False
    has_payroll_lines = False
    allocation_lines = []
    allocation_page_obj = None
    detailed_runs = []

    if filters['ready']:
        runs_qs = _payroll_runs_for_filters(filters, request.user, user_branches)
        runs_count = runs_qs.count()
        has_draft_runs = runs_qs.filter(status=PayrollRun.Status.DRAFT).exists()
        line_prefetch = Prefetch(
            'lines',
            queryset=PayrollLine.objects.select_related('employee').order_by('employee__name'),
        )
        payroll_runs = list(
            runs_qs.prefetch_related(line_prefetch).order_by('branch__name', 'sponsorship__company_name'),
        )

        grand_totals = runs_qs.aggregate(
            total_earnings=Sum('total_earnings'),
            total_deductions=Sum('total_deductions'),
            total_net=Sum('total_net'),
            employees_count=Sum('employees_count'),
        )

        has_payroll_lines = any(run.lines.all() for run in payroll_runs)

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
    saved_drafts_count = _count_saved_draft_runs(filters, request.user, user_branches)
    active_mode = filters.get('salary_mode') or PayrollRun.SalaryMode.TRANSFER
    period_runs = _period_payroll_runs(
        filters, request.user, user_branches, active_mode,
        branch_ids=filters['branch_ids'] or None,
    )
    period_totals = _period_run_totals(period_runs)
    if period_runs:
        has_payroll_lines = any(run.lines.all() for run in period_runs)
    mode_run_counts = _payroll_mode_run_counts(
        filters, request.user, user_branches,
        branch_ids=filters['branch_ids'] or None,
    )
    tab_qs_base = {
        'year': filters['year'],
        'month': filters['month'],
        'branch_ids': filters['branch_ids'] or None,
    }
    tab_qs_transfer = _payroll_list_querystring(
        **tab_qs_base,
        salary_mode=PayrollRun.SalaryMode.TRANSFER,
        sponsorship_ids=filters['sponsorship_ids'],
    )
    tab_qs_cash = _payroll_list_querystring(
        **tab_qs_base,
        salary_mode=PayrollRun.SalaryMode.CASH,
        sponsorship_ids=None,
    )
    modal_runs = period_runs if period_runs else payroll_runs
    if open_run_id and not any(r.pk == open_run_id for r in modal_runs):
        open_run_id = None
    for run in modal_runs:
        run.open_list_url = _payroll_run_open_url(run)
    for run in period_runs:
        if not getattr(run, 'open_list_url', None):
            run.open_list_url = _payroll_run_open_url(run)
    filter_qs = _payroll_list_querystring(
        branch_ids=filters['branch_ids'] if filters['ready'] else None,
        year=filters['year'],
        month=filters['month'],
        salary_mode=filters['salary_mode'] or None,
        sponsorship_ids=filters['sponsorship_ids'],
    )
    export_unified_qs = _payroll_list_querystring(
        year=filters['year'],
        month=filters['month'],
        salary_mode=active_mode,
        sponsorship_ids=filters['sponsorship_ids'] if active_mode == PayrollRun.SalaryMode.TRANSFER else None,
    )
    has_consolidated_run = any(
        r.run_kind == PayrollRun.RunKind.CONSOLIDATED for r in period_runs
    )
    show_unified_run_row = (
        not has_consolidated_run
        and not filters.get('branch_ids')
        and len(period_runs) > 1
    )

    return render(request, 'pages/payroll/list.html', {
        'branches': user_branches,
        'sponsorships': sponsorships,
        'SALARY_MODE_CHOICES': PayrollRun.SalaryMode.choices,
        'current_year': today.year,
        'current_month': today.month,
        'years_range': range(today.year - 2, today.year + 1),
        'months_range': range(1, 13),
        'filter_branch_ids': filters['branch_ids'] or [],
        'all_branches_selected': not filters.get('branch_ids'),
        'filter_year': filters['year'],
        'filter_month': filters['month'],
        'filter_salary_mode': filters['salary_mode'],
        'filter_salary_mode_ids': [filters['salary_mode']] if filters.get('salary_mode') else [],
        'salary_mode_filter_items': SALARY_MODE_FILTER_ITEMS,
        'filter_sponsorship_ids': filters['sponsorship_ids'] or [],
        'filter_qs': filter_qs,
        'payroll_runs': payroll_runs,
        'open_run_id': open_run_id,
        'grand_totals': grand_totals,
        'runs_count': runs_count,
        'show_table': filters['ready'],
        'can_build': user_can_manage_payroll(request.user),
        'has_draft_runs': has_draft_runs,
        'has_payroll_lines': has_payroll_lines,
        'can_export': bool(
            filters.get('year') and filters.get('month') and filters.get('salary_mode') and has_payroll_lines
        ),
        'period_totals': period_totals,
        'export_unified_qs': export_unified_qs,
        'show_unified_run_row': show_unified_run_row,
        'has_consolidated_run': has_consolidated_run,
        'saved_drafts_count': saved_drafts_count,
        'detailed_runs': detailed_runs,
        'allocation_lines': allocation_lines,
        'allocation_page_obj': allocation_page_obj,
        'period_runs': period_runs,
        'mode_run_counts': mode_run_counts,
        'active_salary_mode': active_mode,
        'tab_qs_transfer': tab_qs_transfer,
        'tab_qs_cash': tab_qs_cash,
        'modal_runs': modal_runs,
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

    if run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
        if not request.user.is_superuser:
            allowed = user_branches.values_list('company_id', flat=True).distinct()
            if run.company_id not in allowed:
                raise Http404()
    elif not request.user.is_superuser and run.branch not in user_branches:
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
    if run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
        if not request.user.is_superuser:
            allowed = user_branches.values_list('company_id', flat=True).distinct()
            if run.company_id not in allowed:
                raise Http404()
    elif not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()
    try:
        if run.run_kind == PayrollRun.RunKind.DETAILED:
            from apps.payroll.services.transfer_payroll import build_payroll_detailed_run
            build_payroll_detailed_run(
                run.company, run.period_year, run.period_month, request.user,
                salary_mode=run.salary_mode,
                sponsorship_id=run.sponsorship_id,
            )
        elif run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
            branches = list(
                user_branches.filter(company_id=run.company_id, is_active=True).order_by('name'),
            )
            build_consolidated_payroll_run(
                branches, run.period_year, run.period_month, request.user,
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
    if run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
        if not request.user.is_superuser:
            allowed = user_branches.values_list('company_id', flat=True).distinct()
            if run.company_id not in allowed:
                raise Http404()
    elif not request.user.is_superuser and run.branch not in user_branches:
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
def export_payroll_list_excel(request):
    """تصدير المسير الموحّد (كل الفروع المختارة) إلى Excel."""
    try:
        from apps.payroll.services.export_excel import (
            build_payroll_runs_workbook,
            payroll_runs_excel_filename,
            workbook_to_response,
        )
    except ImportError:
        messages.error(request, 'مكتبة openpyxl غير مثبتة.')
        return redirect('web:list_payroll_runs')

    user_branches = _user_branches(request.user)
    filters = _parse_payroll_form(request, user_branches)
    filters, redirect_response = _restore_payroll_list_filters(
        request, filters, request.user, user_branches,
    )
    if redirect_response is not None:
        return redirect_response
    if not filters.get('year') or not filters.get('month') or not filters.get('salary_mode'):
        messages.error(request, 'يرجى اختيار السنة والشهر ونوع الراتب أولاً.')
        return redirect('web:list_payroll_runs')

    runs = _runs_for_unified_export(filters, request.user, user_branches)
    if not runs:
        messages.error(request, 'لا يوجد مسير للتصدير — ابنِ المسير أولاً.')
        return _redirect_payroll_list(request, filters)

    lines_qs = PayrollLine.objects.filter(run__in=runs)
    if not lines_qs.exists():
        messages.error(request, 'لا توجد أسطر موظفين للتصدير.')
        return _redirect_payroll_list(request, filters)

    wb = build_payroll_runs_workbook(runs)
    filename = payroll_runs_excel_filename(
        year=filters['year'],
        month=filters['month'],
        salary_mode=filters['salary_mode'],
    )
    return workbook_to_response(wb, filename)


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
        PayrollRun.objects.select_related('branch', 'sponsorship', 'company'),
        id=run_id,
    )

    user_branches = _user_branches(request.user)
    if run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
        if not request.user.is_superuser:
            allowed = user_branches.values_list('company_id', flat=True).distinct()
            if run.company_id not in allowed:
                raise Http404()
    elif not request.user.is_superuser and run.branch not in user_branches:
        raise Http404()

    wb = build_payroll_run_workbook(run)
    return workbook_to_response(wb, payroll_run_excel_filename(run))
