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
from dataclasses import dataclass, field
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
    delete_draft_payroll_run,
    lock_payroll_run,
    unlock_payroll_run,
)
from apps.payroll.services.transfer_payroll import (
    build_detailed_runs_for_branches,
    consolidate_detailed_draft_runs,
)


def _user_branches(user):
    """الفروع المتاحة للمستخدم — يعتمد على access_control مع تخزين مؤقت لكل طلب."""
    from apps.core.services.access_control import get_accessible_branch_ids

    branch_ids = get_accessible_branch_ids(user)
    qs = Branch.objects.filter(is_active=True, is_deleted=False)
    if branch_ids is None:
        return qs.order_by('name')
    if not branch_ids:
        return Branch.objects.none()
    return qs.filter(id__in=branch_ids).order_by('name')


@dataclass
class PayrollBranchScope:
    """فروع المسير — تُحمَّل مرة واحدة لكل طلب لتجنب تكرار استعلامات الفروع."""
    branches: list
    _all_branch_ids: list[int] = field(default_factory=list, repr=False)
    _all_branch_id_set: set[int] = field(default_factory=set, repr=False)
    _allowed_company_ids: list[int] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._all_branch_ids = [b.id for b in self.branches]
        self._all_branch_id_set = set(self._all_branch_ids)
        self._allowed_company_ids = list({
            b.company_id for b in self.branches if b.company_id
        })

    @property
    def all_branch_ids(self) -> list[int]:
        return self._all_branch_ids

    @property
    def all_branch_id_set(self) -> set[int]:
        return self._all_branch_id_set

    @property
    def allowed_company_ids(self) -> list[int]:
        return self._allowed_company_ids

    def resolved_branch_ids(self, filters: dict) -> list[int]:
        ids = filters.get('branch_ids')
        if ids:
            return list(dict.fromkeys(ids))
        return self._all_branch_ids

    def company_ids_for(self, branch_ids: list[int]) -> list[int]:
        id_set = set(branch_ids)
        return list({
            b.company_id for b in self.branches
            if b.id in id_set and b.company_id
        })


def _payroll_branch_scope(user) -> PayrollBranchScope:
    cached = getattr(user, '_payroll_branch_scope_cache', None)
    if cached is not None:
        return cached
    scope = PayrollBranchScope(branches=list(_user_branches(user)))
    user._payroll_branch_scope_cache = scope
    return scope


def _payroll_list_querystring(
    *,
    branch_ids=None,
    year=None,
    month=None,
    salary_mode=None,
    sponsorship_ids=None,
    payroll_view=None,
    page=None,
    open_run_id=None,
    alloc_page=None,
    runs_page=None,
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
    if payroll_view == 'detailed':
        pairs.append(('payroll_view', 'detailed'))
    if page:
        pairs.append(('page', page))
    if alloc_page:
        pairs.append(('alloc_page', alloc_page))
    if runs_page:
        pairs.append(('runs_page', runs_page))
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


def _resolved_branch_ids(filters, scope: PayrollBranchScope) -> list[int]:
    """فروع المسير — None في الفلتر = جميع الفروع المتاحة للمستخدم."""
    return scope.resolved_branch_ids(filters)


def _branches_by_company(branches) -> list[list]:
    """تجميع الفروع حسب الشركة — مسير موحّد لكل شركة."""
    groups: dict[int, list] = {}
    for branch in branches:
        groups.setdefault(branch.company_id, []).append(branch)
    return [groups[company_id] for company_id in sorted(groups)]


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
    sponsorship_ids = filters['sponsorship_ids']
    if filters['salary_mode'] == PayrollRun.SalaryMode.CASH:
        sponsorship_ids = None
    request.session[_PAYROLL_LIST_SESSION_KEY] = {
        'branch_ids': list(branch_ids) if branch_ids else None,
        'year': filters['year'],
        'month': filters['month'],
        'salary_mode': filters['salary_mode'],
        'sponsorship_ids': sponsorship_ids,
        'payroll_view': filters.get('payroll_view', 'standard'),
    }
    request.session.modified = True


def _consolidated_runs_qs(filters: dict, user, scope: PayrollBranchScope, branch_ids):
    """مسيرات موحّدة لشركات الفروع المحددة."""
    company_ids = scope.company_ids_for(branch_ids)
    qs = PayrollRun.objects.filter(
        run_kind=PayrollRun.RunKind.CONSOLIDATED,
        period_year=filters['year'],
        period_month=filters['month'],
        salary_mode=filters['salary_mode'],
        company_id__in=company_ids,
    ).select_related('company', 'sponsorship')
    if not user.is_superuser:
        qs = qs.filter(company_id__in=scope.allowed_company_ids)
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


def _user_may_access_payroll_run(user, run: PayrollRun, scope: PayrollBranchScope) -> bool:
    if user.is_superuser:
        return True
    if run.run_kind in (PayrollRun.RunKind.CONSOLIDATED, PayrollRun.RunKind.DETAILED):
        return run.company_id in scope.allowed_company_ids
    return bool(run.branch_id and run.branch_id in scope.all_branch_id_set)


def _prune_empty_consolidated_drafts(filters: dict, user, scope: PayrollBranchScope, salary_mode: str) -> int:
    """إزالة مسودات موحّدة فارغة (بدون موظفين) من العرض."""
    branch_ids = _resolved_branch_ids(filters, scope)
    if not _prefer_consolidated_runs(filters, branch_ids):
        return 0
    mode_filters = dict(filters)
    mode_filters['salary_mode'] = salary_mode
    qs = _consolidated_runs_qs(mode_filters, user, scope, branch_ids)
    empty_ids = list(
        qs.filter(
            status=PayrollRun.Status.DRAFT,
            employees_count=0,
        ).values_list('id', flat=True),
    )
    if empty_ids:
        for run in PayrollRun.objects.filter(id__in=empty_ids):
            run.hard_delete()
    return len(empty_ids)


def _draft_runs_for_period(filters: dict, user, scope: PayrollBranchScope, *, branch_ids=None):
    """مسودات لشهر محدد (موحّدة أو STANDARD حسب الفلاتر)."""
    year, month = filters.get('year'), filters.get('month')
    if not year or not month:
        return []
    resolved = branch_ids or _resolved_branch_ids(filters, scope)
    if _prefer_consolidated_runs(filters, resolved):
        qs = PayrollRun.objects.filter(
            period_year=year,
            period_month=month,
            run_kind=PayrollRun.RunKind.CONSOLIDATED,
            status=PayrollRun.Status.DRAFT,
        )
        if not user.is_superuser:
            qs = qs.filter(company_id__in=scope.allowed_company_ids)
        return list(qs.select_related('company', 'sponsorship').order_by('-updated_at'))
    qs = PayrollRun.objects.filter(
        period_year=year,
        period_month=month,
        run_kind=PayrollRun.RunKind.STANDARD,
        status=PayrollRun.Status.DRAFT,
    )
    if not user.is_superuser:
        qs = qs.filter(branch_id__in=scope.all_branch_ids)
    if branch_ids:
        qs = qs.filter(branch_id__in=branch_ids)
    return list(qs.select_related('branch', 'sponsorship').order_by('-updated_at'))


def _payroll_line_prefetch():
    return Prefetch(
        'lines',
        queryset=PayrollLine.objects.select_related('employee').order_by('employee__name'),
    )


def _period_payroll_run_count(
    filters: dict, user, scope: PayrollBranchScope, salary_mode: str, *, branch_ids=None,
) -> int:
    """عدد مسيرات الشهر ونوع الراتب — بدون تحميل الأسطر."""
    year, month = filters.get('year'), filters.get('month')
    if not year or not month or salary_mode not in PayrollRun.SalaryMode.values:
        return 0
    resolved = branch_ids if branch_ids is not None else _resolved_branch_ids(filters, scope)
    if _prefer_consolidated_runs(filters, resolved):
        mode_filters = dict(filters)
        mode_filters['salary_mode'] = salary_mode
        qs = _consolidated_runs_qs(mode_filters, user, scope, resolved)
        count = qs.count()
        if count:
            return count
    qs = PayrollRun.objects.filter(
        period_year=year,
        period_month=month,
        run_kind=PayrollRun.RunKind.STANDARD,
        salary_mode=salary_mode,
    )
    if not user.is_superuser:
        qs = qs.filter(branch_id__in=scope.all_branch_ids)
    if branch_ids:
        qs = qs.filter(branch_id__in=branch_ids)
    return qs.count()


def _period_payroll_runs(filters: dict, user, scope: PayrollBranchScope, salary_mode: str, *, branch_ids=None):
    """مسيرات الشهر ونوع الراتب — موحّدة أو حسب الفرع."""
    year, month = filters.get('year'), filters.get('month')
    if not year or not month or salary_mode not in PayrollRun.SalaryMode.values:
        return []
    resolved = branch_ids if branch_ids is not None else _resolved_branch_ids(filters, scope)
    line_prefetch = _payroll_line_prefetch()
    if _prefer_consolidated_runs(filters, resolved):
        mode_filters = dict(filters)
        mode_filters['salary_mode'] = salary_mode
        qs = _consolidated_runs_qs(mode_filters, user, scope, resolved)
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
        qs = qs.filter(branch_id__in=scope.all_branch_ids)
    if branch_ids:
        qs = qs.filter(branch_id__in=branch_ids)
    return list(
        qs.prefetch_related(line_prefetch)
        .order_by('status', 'branch__name', 'sponsorship__company_name', 'id'),
    )


def _payroll_mode_run_counts(filters: dict, user, scope: PayrollBranchScope, *, branch_ids=None) -> dict[str, int]:
    return {
        mode: _period_payroll_run_count(
            filters, user, scope, mode, branch_ids=branch_ids,
        )
        for mode in PayrollRun.SalaryMode.values
    }


def _modal_runs_for_list(period_runs, open_run_id):
    """مسيرات النافذة المنبثقة — الصفحة الحالية + المسير المفتوح إن وُجد."""
    modal_runs = list(period_runs)
    if not open_run_id or any(r.pk == open_run_id for r in modal_runs):
        return modal_runs
    extra = (
        PayrollRun.objects.filter(pk=open_run_id)
        .select_related('branch', 'sponsorship', 'company')
        .prefetch_related(_payroll_line_prefetch())
        .first()
    )
    if extra:
        return [extra, *modal_runs]
    return modal_runs


def _period_run_totals(runs: list) -> dict:
    from decimal import Decimal
    return {
        'runs_count': len(runs),
        'employees_count': sum(int(r.employees_count or 0) for r in runs),
        'total_earnings': sum(Decimal(r.total_earnings or 0) for r in runs),
        'total_deductions': sum(Decimal(r.total_deductions or 0) for r in runs),
        'total_net': sum(Decimal(r.total_net or 0) for r in runs),
    }


def _runs_for_unified_export(filters: dict, user, scope: PayrollBranchScope):
    """كل مسيرات الشهر/النوع في ملف تصدير واحد — بغض النظر عن فلتر فرع العرض."""
    export_filters = dict(filters)
    export_filters['branch_ids'] = None
    return list(_payroll_runs_for_filters(export_filters, user, scope))


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


def _infer_payroll_filters_from_drafts(filters: dict, user, scope: PayrollBranchScope) -> dict:
    """استنتاج الفروع/النوع/الكفالة من مسودات محفوظة لنفس الشهر."""
    if filters.get('salary_mode'):
        return filters

    year, month = filters.get('year'), filters.get('month')
    if not year or not month:
        return filters

    branch_ids = filters.get('branch_ids') or None
    runs = _draft_runs_for_period(filters, user, scope, branch_ids=branch_ids)
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


def _payroll_filters_explicitly_submitted(request) -> bool:
    if not request or request.method != 'GET':
        return False
    return (request.GET.get('payroll_filters') or '').strip() == '1'


def _merge_stored_payroll_filters(
    filters: dict,
    stored: dict,
    *,
    restore_payroll_view: bool = True,
    request=None,
) -> dict:
    if request and _payroll_filters_explicitly_submitted(request):
        if (
            restore_payroll_view
            and stored.get('payroll_view')
            and not (request.GET.get('payroll_view') or '').strip()
        ):
            filters['payroll_view'] = stored['payroll_view']
        return filters

    if 'branch_ids' in stored and not filters.get('branch_ids'):
        stored_branches = stored['branch_ids']
        filters['branch_ids'] = list(stored_branches) if stored_branches else None
    if stored.get('salary_mode') and not filters.get('salary_mode'):
        filters['salary_mode'] = stored['salary_mode']
    if (
        filters.get('salary_mode') != PayrollRun.SalaryMode.CASH
        and 'sponsorship_ids' in stored
        and filters.get('sponsorship_ids') is None
    ):
        filters['sponsorship_ids'] = stored['sponsorship_ids']
    if filters.get('salary_mode') == PayrollRun.SalaryMode.CASH:
        filters['sponsorship_ids'] = None
    has_explicit_year = bool((request.GET.get('year') or '').strip()) if request else False
    has_explicit_month = bool((request.GET.get('month') or '').strip()) if request else False
    if stored.get('year') and not has_explicit_year:
        filters['year'] = stored['year']
    if stored.get('month') and not has_explicit_month:
        filters['month'] = stored['month']
    if restore_payroll_view and stored.get('payroll_view'):
        filters['payroll_view'] = stored['payroll_view']
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


def _restore_payroll_list_filters(request, filters: dict, user, scope: PayrollBranchScope):
    """استعادة آخر فلاتر أو مسودات محفوظة عند فتح الصفحة."""
    filters = _default_payroll_period(filters)
    if request.method != 'GET':
        return _recompute_payroll_ready(filters), None

    explicit_detailed_view = (
        request.method == 'GET'
        and (request.GET.get('payroll_view') or '').strip() == 'detailed'
    )
    restore_payroll_view = not explicit_detailed_view
    if request.method == 'GET' and (request.GET.get('salary_mode') or '').strip():
        restore_payroll_view = False

    stored = request.session.get(_PAYROLL_LIST_SESSION_KEY)
    if stored:
        filters = _merge_stored_payroll_filters(
            filters,
            stored,
            restore_payroll_view=restore_payroll_view,
            request=request,
        )

    filters = _infer_payroll_filters_from_drafts(filters, user, scope)
    if not filters.get('salary_mode'):
        filters['salary_mode'] = PayrollRun.SalaryMode.TRANSFER
    filters = _recompute_payroll_ready(filters)

    redirect_response = None
    if _payroll_filters_missing_from_query(request, filters):
        redirect_response = _redirect_payroll_list(request, filters)
    return filters, redirect_response


def _count_saved_draft_runs(filters: dict, user, scope: PayrollBranchScope) -> int:
    year, month = filters.get('year'), filters.get('month')
    if not year or not month:
        return 0
    branch_ids = _resolved_branch_ids(filters, scope)
    if _prefer_consolidated_runs(filters, branch_ids):
        qs = PayrollRun.objects.filter(
            period_year=year,
            period_month=month,
            run_kind=PayrollRun.RunKind.CONSOLIDATED,
            status=PayrollRun.Status.DRAFT,
        )
        if not user.is_superuser:
            qs = qs.filter(company_id__in=scope.allowed_company_ids)
        return qs.count()
    qs = PayrollRun.objects.filter(
        period_year=year,
        period_month=month,
        run_kind=PayrollRun.RunKind.STANDARD,
        status=PayrollRun.Status.DRAFT,
    )
    if not user.is_superuser:
        qs = qs.filter(branch_id__in=scope.all_branch_ids)
    if filters.get('branch_ids'):
        qs = qs.filter(branch_id__in=filters['branch_ids'])
    return qs.count()


def _parse_payroll_form(request, scope: PayrollBranchScope):
    """قراءة معايير المسير من GET أو POST."""
    accessible = None if request.user.is_superuser else scope.all_branch_ids
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
    view_raw = (src.get('payroll_view') or '').strip()
    payroll_view = 'detailed' if view_raw == 'detailed' else 'standard'

    year = month = None
    try:
        if year_raw:
            year = int(year_raw)
        if month_raw:
            month = int(month_raw)
    except ValueError:
        pass

    if salary_mode == PayrollRun.SalaryMode.CASH:
        sponsorship_ids = None
    filters = {
        'branch_ids': branch_ids,
        'year': year,
        'month': month,
        'salary_mode': salary_mode,
        'sponsorship_ids': sponsorship_ids,
        'payroll_view': payroll_view,
        'ready': False,
    }
    return _recompute_payroll_ready(_default_payroll_period(filters))


def _validate_payroll_build(filters, scope: PayrollBranchScope):
    """التحقق من صحة معايير البناء. يُرجع رسالة خطأ أو None."""
    if not _resolved_branch_ids(filters, scope):
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


def _build_payroll_runs(request, filters, scope: PayrollBranchScope):
    """بناء مسير موحّد (عدة فروع) أو مسير لكل فرع (فرع واحد)."""
    from django.db import transaction

    branch_ids = _resolved_branch_ids(filters, scope)
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
    use_consolidated = _prefer_consolidated_runs(filters, branch_ids)
    try:
        with transaction.atomic():
            for sponsorship_id in sponsorship_ids:
                if use_consolidated:
                    for company_branches in _branches_by_company(branches):
                        try:
                            built = build_consolidated_payroll_run(
                                company_branches, filters['year'], filters['month'], request.user,
                                salary_mode=filters['salary_mode'],
                                sponsorship_id=sponsorship_id,
                            )
                            if built:
                                runs_built.append(built)
                        except ValueError as e:
                            sp_label = f' / كفالة #{sponsorship_id}' if sponsorship_id else ''
                            company_label = company_branches[0].company.name
                            errors.append(f'{company_label} — مسير موحّد{sp_label}: {e}')
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


def _payroll_runs_for_filters(filters, user, scope: PayrollBranchScope):
    """مسيرات مطابقة للمعايير — موحّدة أو حسب الفرع."""
    branch_ids = _resolved_branch_ids(filters, scope)
    if _prefer_consolidated_runs(filters, branch_ids):
        qs = _consolidated_runs_qs(filters, user, scope, branch_ids)
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
        qs = qs.filter(branch_id__in=scope.all_branch_ids)
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        sp_ids = filters.get('sponsorship_ids')
        if sp_ids is not None:
            qs = qs.filter(sponsorship_id__in=sp_ids)
    else:
        qs = qs.filter(sponsorship__isnull=True)
    return qs.order_by('branch__name')


def _detailed_runs_for_filters(filters, user, scope: PayrollBranchScope):
    """مسيرات تفصيلية موحّدة للشركات المرتبطة بالفروع المختارة."""
    branch_ids = _resolved_branch_ids(filters, scope)
    company_ids = scope.company_ids_for(branch_ids)
    qs = PayrollRun.objects.filter(
        company_id__in=company_ids,
        period_year=filters['year'],
        period_month=filters['month'],
        salary_mode=filters['salary_mode'],
        run_kind=PayrollRun.RunKind.DETAILED,
    ).select_related('company', 'sponsorship')
    if not user.is_superuser:
        qs = qs.filter(company_id__in=scope.allowed_company_ids)
    runs = list(qs.order_by('period_year', 'period_month', 'company__name'))
    unified = [r for r in runs if r.sponsorship_id is None]
    if unified:
        return unified
    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER:
        sp_ids = filters.get('sponsorship_ids')
        if sp_ids is not None:
            sp_set = set(sp_ids)
            return [r for r in runs if r.sponsorship_id in sp_set]
    return [r for r in runs if r.sponsorship_id is None]


def _build_detailed_payroll_runs(request, filters, scope: PayrollBranchScope):
    from django.db import transaction

    branch_ids = _resolved_branch_ids(filters, scope)
    branches = list(Branch.objects.filter(id__in=branch_ids, is_active=True).order_by('name'))
    if len(branches) != len(branch_ids):
        return [], ['أحد الفروع المختارة غير صالح أو غير متاح لحسابك.'], False

    company_ids = list(
        Branch.objects.filter(id__in=branch_ids)
        .values_list('company_id', flat=True)
        .distinct(),
    )
    had_detailed_draft = PayrollRun.objects.filter(
        company_id__in=company_ids,
        period_year=filters['year'],
        period_month=filters['month'],
        salary_mode=filters['salary_mode'],
        run_kind=PayrollRun.RunKind.DETAILED,
        status=PayrollRun.Status.DRAFT,
    ).exists()

    consolidate_detailed_draft_runs(
        company_ids=company_ids,
        year=filters['year'],
        month=filters['month'],
        salary_mode=filters['salary_mode'],
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
                sponsorship_scope_ids=(
                    _effective_sponsorship_ids(filters)
                    if filters['salary_mode'] == PayrollRun.SalaryMode.TRANSFER
                    else None
                ),
            )
    except ValueError as e:
        errors.append(str(e))
    return runs_built, errors, had_detailed_draft


def _financial_audit_for_list(filters, user, scope: PayrollBranchScope, *, payroll_view: str, period_runs, detailed_runs):
    from apps.payroll.services.financial_audit import audit_payroll_runs

    if payroll_view == 'detailed':
        return audit_payroll_runs(detailed_runs)
    return audit_payroll_runs(period_runs)


def _lock_payroll_runs_for_filters(request, filters, user, scope: PayrollBranchScope):
    """ترحيل كل مسيرات STANDARD المطابقة للفلاتر. يُرجع (locked_count, errors)."""
    runs = list(_payroll_runs_for_filters(filters, user, scope))
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
        payroll_view=filters.get('payroll_view'),
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
    scope = _payroll_branch_scope(request.user)
    filters = _parse_payroll_form(request, scope)
    filters, redirect_response = _restore_payroll_list_filters(
        request, filters, request.user, scope,
    )
    if redirect_response is not None:
        return redirect_response

    if request.method == 'POST':
        payroll_action = (request.POST.get('payroll_action') or '').strip()
        build_kind = (request.POST.get('build_kind') or '').strip()

        if not user_can_manage_payroll(request.user):
            messages.error(request, 'ليس لديك صلاحية إدارة المسير.')
        else:
            err = _validate_payroll_build(filters, scope)
            if err:
                messages.error(request, err)
            elif payroll_action == 'lock':
                runs_to_audit = [
                    r for r in _payroll_runs_for_filters(filters, request.user, scope)
                    if r.status == PayrollRun.Status.DRAFT
                ]
                from apps.payroll.services.financial_audit import audit_payroll_runs
                audit = audit_payroll_runs(runs_to_audit)
                if not audit.ready_to_lock:
                    messages.error(
                        request,
                        'تعذّر الإغلاق النهائي: تقرير التحقق المالي يحتوي على أخطاء. '
                        'راجع التقرير ثم أعد بناء المسودة.',
                    )
                    shown = 0
                    for check in audit.checks:
                        if check.level != 'error':
                            continue
                        label = check.employee_name or check.run_label or check.title
                        messages.error(request, f'{label}: {check.detail}')
                        shown += 1
                        if shown >= 5:
                            break
                else:
                    locked, lock_errors = _lock_payroll_runs_for_filters(
                        request, filters, request.user, scope,
                    )
                    for e in lock_errors:
                        messages.error(request, e)
                    if locked:
                        messages.success(
                            request,
                            f'تم الإغلاق النهائي لـ {locked} مسير وربط بنود الخصم.',
                        )
            elif payroll_action == 'save' or build_kind == 'standard':
                had_standard_draft = bool(
                    _draft_runs_for_period(filters, request.user, scope),
                )
                runs_built, build_errors = _build_payroll_runs(request, filters, scope)
                for e in build_errors:
                    messages.error(request, e)
                if runs_built:
                    total_emp = sum(r.employees_count for r in runs_built)
                    if payroll_action == 'save':
                        verb = 'إعادة حفظ' if had_standard_draft else 'حفظ'
                        messages.success(
                            request,
                            f'تم {verb} المسير كمسودة ({total_emp} موظف).',
                        )
                    else:
                        mode_label = dict(PayrollRun.SalaryMode.choices).get(
                            filters['salary_mode'], filters['salary_mode'],
                        )
                        if had_standard_draft:
                            if any(r.run_kind == PayrollRun.RunKind.CONSOLIDATED for r in runs_built):
                                messages.success(
                                    request,
                                    f'تم إعادة بناء المسير الموحّد {mode_label} '
                                    f'واستبدال المسودة السابقة ({total_emp} موظف).',
                                )
                            else:
                                messages.success(
                                    request,
                                    f'تم إعادة بناء المسير {mode_label} '
                                    f'واستبدال المسودة السابقة ({total_emp} موظف).',
                                )
                        elif any(r.run_kind == PayrollRun.RunKind.CONSOLIDATED for r in runs_built):
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
                runs_built, build_errors, had_detailed_draft = _build_detailed_payroll_runs(
                    request, filters, scope,
                )
                for e in build_errors:
                    messages.error(request, e)
                if runs_built:
                    total_rows = sum(r.employees_count for r in runs_built)
                    if had_detailed_draft:
                        messages.success(
                            request,
                            f'تم إعادة بناء المسير التفصيلي واستبدال المسودة السابقة '
                            f'({total_rows} موظف منقول).',
                        )
                    elif len(runs_built) == 1:
                        messages.success(
                            request,
                            f'تم بناء مسير تفصيلي موحّد '
                            f'({total_rows} موظف منقول — مسودة واحدة لكل الفروع).',
                        )
                    else:
                        messages.success(
                            request,
                            f'تم بناء {len(runs_built)} مسير تفصيلي '
                            f'({total_rows} موظف منقول).',
                        )
                    filters['payroll_view'] = 'detailed'
                    return _redirect_payroll_list(
                        request, filters, open_run_id=runs_built[0].pk,
                    )
        return _redirect_payroll_list(request, filters)

    if request.method == 'GET' and filters['ready']:
        _store_payroll_list_filters(request, filters)

    open_run_id = _parse_open_run_id(request)
    grand_totals = {}
    runs_count = 0
    has_draft_runs = False
    has_payroll_lines = False
    detailed_runs = []
    detailed_runs_all = []
    detailed_runs_page_obj = None
    detailed_runs_start_index = 1
    detailed_runs_total_count = 0

    active_payroll_view = filters.get('payroll_view', 'standard')
    detailed_runs = []
    detailed_totals = {}
    detailed_run_count = 0
    has_detailed_draft = False
    if filters['ready'] and active_payroll_view == 'detailed':
        detailed_runs_all = list(
            _detailed_runs_for_filters(filters, request.user, scope),
        )
        from django.core.paginator import Paginator
        detailed_runs_paginator = Paginator(detailed_runs_all, 6)
        detailed_runs_page_obj = detailed_runs_paginator.get_page(
            request.GET.get('runs_page') or 1,
        )
        detailed_runs = list(detailed_runs_page_obj.object_list)
        detailed_runs_start_index = detailed_runs_page_obj.start_index()
        detailed_runs_total_count = len(detailed_runs_all)
        has_detailed_draft = any(
            r.status == PayrollRun.Status.DRAFT for r in detailed_runs_all
        )
        detailed_run_count = detailed_runs_total_count
        detailed_totals = _period_run_totals(detailed_runs_all)
        has_payroll_lines = any(int(r.employees_count or 0) > 0 for r in detailed_runs_all)
    elif filters['ready']:
        detailed_run_count = len(_detailed_runs_for_filters(
            filters, request.user, scope,
        ))

    today = date.today()
    sponsorships = Sponsorship.objects.filter(is_deleted=False, is_active=True).order_by('company_name')
    saved_drafts_count = _count_saved_draft_runs(filters, request.user, scope)
    active_mode = filters.get('salary_mode') or PayrollRun.SalaryMode.TRANSFER
    if filters['ready'] and active_payroll_view != 'detailed':
        _prune_empty_consolidated_drafts(filters, request.user, scope, active_mode)
    if active_payroll_view == 'detailed':
        period_runs_all = []
        period_totals = _period_run_totals(period_runs_all)
    else:
        period_runs_all = _period_payroll_runs(
            filters, request.user, scope, active_mode,
            branch_ids=filters['branch_ids'] or None,
        )
        period_totals = _period_run_totals(period_runs_all)
    if filters['ready']:
        if active_payroll_view == 'detailed':
            has_draft_runs = has_detailed_draft
        else:
            has_draft_runs = any(r.status == PayrollRun.Status.DRAFT for r in period_runs_all)
            has_payroll_lines = any(int(r.employees_count or 0) > 0 for r in period_runs_all)
            runs_count = period_totals['runs_count']
            grand_totals = {
                'total_earnings': period_totals['total_earnings'],
                'total_deductions': period_totals['total_deductions'],
                'total_net': period_totals['total_net'],
                'employees_count': period_totals['employees_count'],
            }
    from django.core.paginator import Paginator
    runs_paginator = Paginator(period_runs_all, 6)
    period_runs_page_obj = runs_paginator.get_page(request.GET.get('runs_page') or 1)
    period_runs = list(period_runs_page_obj.object_list)
    runs_start_index = period_runs_page_obj.start_index()
    mode_run_counts = _payroll_mode_run_counts(
        filters, request.user, scope,
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
    tab_qs_detailed = _payroll_list_querystring(
        **tab_qs_base,
        salary_mode=active_mode,
        sponsorship_ids=filters['sponsorship_ids'] if active_mode == PayrollRun.SalaryMode.TRANSFER else None,
        payroll_view='detailed',
    )
    modal_source = detailed_runs if active_payroll_view == 'detailed' else period_runs
    modal_runs = _modal_runs_for_list(modal_source, open_run_id)
    if open_run_id and not any(r.pk == open_run_id for r in modal_runs):
        open_run_id = None
    for run in modal_runs:
        run.open_list_url = _payroll_run_open_url(run)
    active_runs_page = None
    if active_payroll_view == 'detailed':
        if detailed_runs_page_obj and detailed_runs_page_obj.number > 1:
            active_runs_page = detailed_runs_page_obj.number
    elif period_runs_page_obj.number > 1:
        active_runs_page = period_runs_page_obj.number
    filter_qs = _payroll_list_querystring(
        branch_ids=filters['branch_ids'] if filters['ready'] else None,
        year=filters['year'],
        month=filters['month'],
        salary_mode=filters['salary_mode'] or None,
        sponsorship_ids=filters['sponsorship_ids'],
        payroll_view=active_payroll_view if active_payroll_view == 'detailed' else None,
        runs_page=active_runs_page,
    )
    export_unified_qs = _payroll_list_querystring(
        year=filters['year'],
        month=filters['month'],
        salary_mode=active_mode,
        sponsorship_ids=filters['sponsorship_ids'] if active_mode == PayrollRun.SalaryMode.TRANSFER else None,
    )
    has_consolidated_run = any(
        r.run_kind == PayrollRun.RunKind.CONSOLIDATED for r in period_runs_all
    )
    show_unified_run_row = (
        not has_consolidated_run
        and not filters.get('branch_ids')
        and len(period_runs_all) > 1
        and period_runs_page_obj.number == 1
    )
    runs_page_base_qs = _payroll_list_querystring(
        branch_ids=filters['branch_ids'] if filters['ready'] else None,
        year=filters['year'],
        month=filters['month'],
        salary_mode=filters['salary_mode'] or None,
        sponsorship_ids=filters['sponsorship_ids'],
        payroll_view=active_payroll_view if active_payroll_view == 'detailed' else None,
    )
    period_runs_total_count = len(period_runs_all)
    financial_audit = None
    if filters['ready'] and has_draft_runs:
        financial_audit = _financial_audit_for_list(
            filters,
            request.user,
            scope,
            payroll_view=active_payroll_view,
            period_runs=period_runs_all,
            detailed_runs=detailed_runs_all,
        )

    return render(request, 'pages/payroll/list.html', {
        'branches': scope.branches,
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
        'all_sponsorships_selected': (
            filters.get('salary_mode') == PayrollRun.SalaryMode.TRANSFER
            and filters.get('sponsorship_ids') is None
        ),
        'filter_qs': filter_qs,
        'payroll_runs': period_runs_all,
        'open_run_id': open_run_id,
        'grand_totals': grand_totals,
        'runs_count': runs_count,
        'show_table': filters['ready'],
        'can_build': user_can_manage_payroll(request.user),
        'can_build_new': (
            user_can_manage_payroll(request.user)
            and bool(filters.get('year') and filters.get('month'))
            and not has_draft_runs
        ),
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
        'detailed_runs_all': detailed_runs_all,
        'detailed_runs_page_obj': detailed_runs_page_obj,
        'detailed_runs_start_index': detailed_runs_start_index,
        'detailed_runs_total_count': detailed_runs_total_count,
        'period_runs': period_runs,
        'period_runs_all': period_runs_all,
        'period_runs_page_obj': period_runs_page_obj,
        'period_runs_total_count': period_runs_total_count,
        'runs_start_index': runs_start_index,
        'runs_page_base_qs': runs_page_base_qs,
        'mode_run_counts': mode_run_counts,
        'active_salary_mode': active_mode,
        'tab_qs_transfer': tab_qs_transfer,
        'tab_qs_cash': tab_qs_cash,
        'tab_qs_detailed': tab_qs_detailed,
        'active_payroll_view': active_payroll_view,
        'detailed_totals': detailed_totals,
        'detailed_run_count': detailed_run_count,
        'has_detailed_draft': has_detailed_draft,
        'prefer_unified_detailed': _prefer_consolidated_runs(
            filters, _resolved_branch_ids(filters, scope),
        ),
        'modal_runs': modal_runs,
        'financial_audit': financial_audit,
    })


def _filters_from_session_or_run(request, run: PayrollRun) -> dict:
    """استعادة فلاتر القائمة بعد حذف مسودة."""
    stored = request.session.get(_PAYROLL_LIST_SESSION_KEY) or {}
    filters = {
        'branch_ids': stored.get('branch_ids'),
        'year': stored.get('year') or run.period_year,
        'month': stored.get('month') or run.period_month,
        'salary_mode': stored.get('salary_mode') or run.salary_mode,
        'sponsorship_ids': stored.get('sponsorship_ids'),
        'payroll_view': stored.get('payroll_view') or (
            'detailed' if run.run_kind == PayrollRun.RunKind.DETAILED else 'standard'
        ),
    }
    return _recompute_payroll_ready(filters)


@login_required
@permission_required('payroll.manage')
def delete_payroll_draft_run(request, run_id):
    """حذف مسودة مسير من قائمة المسيرات."""
    if request.method != 'POST':
        raise Http404()

    run = get_object_or_404(
        PayrollRun.objects.select_related('branch', 'company', 'sponsorship'),
        id=run_id,
    )
    scope = _payroll_branch_scope(request.user)
    if not _user_may_access_payroll_run(request.user, run, scope):
        raise Http404()

    filters = _filters_from_session_or_run(request, run)
    try:
        delete_draft_payroll_run(run)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'تم حذف المسودة.')

    return _redirect_payroll_list(request, filters)


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
    scope = _payroll_branch_scope(request.user)
    if run.run_kind == PayrollRun.RunKind.DETAILED:
        if not request.user.is_superuser:
            if run.company_id not in scope.allowed_company_ids:
                raise Http404()
        from django.core.paginator import Paginator
        from apps.core.utils.pagination import clamp_page_size
        from apps.payroll.models import PayrollAllocationLine

        alloc_qs = run.allocation_lines.select_related(
            'employee', 'branch', 'from_branch',
        ).order_by(
            'employee__name',
            'bears_salary',
            'days_in_branch',
            'transfer_date',
            'id',
        )
        paginator = Paginator(
            alloc_qs,
            per_page=clamp_page_size(request.GET.get('per_page'), default=50, maximum=200),
        )
        page_obj = paginator.get_page(request.GET.get('page') or 1)
        from apps.payroll.services.financial_audit import audit_payroll_runs
        financial_audit = (
            audit_payroll_runs([run])
            if run.status == PayrollRun.Status.DRAFT
            else None
        )
        return render(request, 'pages/payroll/view_detailed.html', {
            'run': run,
            'allocation_lines': page_obj.object_list,
            'page_obj': page_obj,
            'lines_total': paginator.count,
            'financial_audit': financial_audit,
        })

    if run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
        if not request.user.is_superuser:
            if run.company_id not in scope.allowed_company_ids:
                raise Http404()
    elif not request.user.is_superuser and run.branch_id not in scope.all_branch_id_set:
        raise Http404()

    from django.core.paginator import Paginator
    from apps.core.utils.pagination import clamp_page_size

    lines_qs = run.lines.select_related('employee', 'employee__branch').order_by('employee__name')
    paginator = Paginator(
        lines_qs,
        per_page=clamp_page_size(request.GET.get('per_page'), default=50, maximum=200),
    )
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    from apps.payroll.services.financial_audit import audit_payroll_runs
    financial_audit = (
        audit_payroll_runs([run])
        if run.status == PayrollRun.Status.DRAFT
        else None
    )
    return render(request, 'pages/payroll/view.html', {
        'run': run,
        'lines': page_obj.object_list,
        'page_obj': page_obj,
        'lines_total': paginator.count,
        'financial_audit': financial_audit,
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
    scope = _payroll_branch_scope(request.user)
    if run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
        if not request.user.is_superuser:
            if run.company_id not in scope.allowed_company_ids:
                raise Http404()
    elif not request.user.is_superuser and run.branch_id not in scope.all_branch_id_set:
        raise Http404()
    try:
        if run.run_kind == PayrollRun.RunKind.DETAILED:
            from apps.payroll.services.transfer_payroll import build_payroll_detailed_run
            build_payroll_detailed_run(
                run.company, run.period_year, run.period_month, request.user,
                salary_mode=run.salary_mode,
                sponsorship_scope_ids=(
                    [run.sponsorship_id] if run.sponsorship_id else None
                ),
            )
        elif run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
            branches = sorted(
                (b for b in scope.branches if b.company_id == run.company_id and b.is_active),
                key=lambda b: b.name,
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
    scope = _payroll_branch_scope(request.user)
    if run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
        if not request.user.is_superuser:
            if run.company_id not in scope.allowed_company_ids:
                raise Http404()
    elif not request.user.is_superuser and run.branch_id not in scope.all_branch_id_set:
        raise Http404()
    from apps.payroll.services.financial_audit import audit_payroll_runs
    audit = audit_payroll_runs([run])
    if not audit.ready_to_lock:
        messages.error(
            request,
            'تعذّر الترحيل: تقرير التحقق المالي يحتوي على أخطاء.',
        )
        for check in audit.checks:
            if check.level == 'error':
                messages.error(request, f'{check.title}: {check.detail}')
                break
        return redirect('web:view_payroll_run', run_id=run.id)
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

    scope = _payroll_branch_scope(request.user)
    filters = _parse_payroll_form(request, scope)
    filters, redirect_response = _restore_payroll_list_filters(
        request, filters, request.user, scope,
    )
    if redirect_response is not None:
        return redirect_response
    if not filters.get('year') or not filters.get('month') or not filters.get('salary_mode'):
        messages.error(request, 'يرجى اختيار السنة والشهر ونوع الراتب أولاً.')
        return redirect('web:list_payroll_runs')

    runs = _runs_for_unified_export(filters, request.user, scope)
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
            build_payroll_detailed_run_workbook,
            build_payroll_run_workbook,
            payroll_detailed_run_excel_filename,
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

    scope = _payroll_branch_scope(request.user)
    if not _user_may_access_payroll_run(request.user, run, scope):
        raise Http404()

    if run.run_kind == PayrollRun.RunKind.DETAILED:
        wb = build_payroll_detailed_run_workbook(run)
        filename = payroll_detailed_run_excel_filename(run)
    else:
        wb = build_payroll_run_workbook(run)
        filename = payroll_run_excel_filename(run)
    return workbook_to_response(wb, filename)
