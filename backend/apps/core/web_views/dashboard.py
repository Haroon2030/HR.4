"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.web_views._helpers import (
    admin_required, _is_branch_manager, branch_manager_required,
    _user_accessible_branch_ids, employee_branch_access_required, _can_review_action,
)

@login_required
def dashboard_view(request):
    """لوحة التحكم الرئيسية"""
    from django.db.models import Count, Q
    from django.urls import reverse
    from django.core.paginator import Paginator
    from apps.employees.models import EmploymentRequest, Employee
    from apps.core.models import PendingAction, Branch
    from apps.core.web_views._helpers import _is_hr_officer, _is_general_manager
    from apps.core.web_views.employment_requests import get_hr_officers

    # ─── إحصائيات عامة (KPIs) ──────────────────────────────────────
    accessible_branch_ids = list(_user_accessible_branch_ids(request.user) or [])
    emp_qs_all = Employee.objects.filter(is_deleted=False)
    if not request.user.is_superuser and accessible_branch_ids:
        emp_qs_all = emp_qs_all.filter(branch_id__in=accessible_branch_ids)

    emp_status_counts = emp_qs_all.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status=Employee.Status.ACTIVE)),
        leave=Count('id', filter=Q(status=Employee.Status.LEAVE)),
        suspended=Count('id', filter=Q(status=Employee.Status.SUSPENDED)),
        terminated=Count('id', filter=Q(status=Employee.Status.TERMINATED)),
    )

    # طلبات التوظيف المعلقة (لكل المراحل)
    er_qs = EmploymentRequest.objects.filter(is_deleted=False)
    if not request.user.is_superuser and accessible_branch_ids:
        er_qs = er_qs.filter(branch_id__in=accessible_branch_ids)
    er_open_count = er_qs.exclude(status__in=[
        EmploymentRequest.Status.APPROVED,
        EmploymentRequest.Status.REJECTED,
    ]).count()

    # عمليات معلّقة (إجازات / رواتب / نقل ...)
    pa_qs = PendingAction.objects.filter(is_deleted=False) if hasattr(PendingAction, 'is_deleted') else PendingAction.objects.all()
    if not request.user.is_superuser and accessible_branch_ids:
        pa_qs = pa_qs.filter(branch_id__in=accessible_branch_ids)
    pa_open_count = pa_qs.exclude(status__in=[
        PendingAction.Status.APPROVED,
    ]).count()

    # توزيع الموظفين حسب الفرع (Top 6)
    branch_distribution = list(
        emp_qs_all.values('branch__name')
        .annotate(c=Count('id'))
        .order_by('-c')[:6]
    )
    max_branch = max((b['c'] for b in branch_distribution), default=1) or 1

    stats = {
        'employees_total': emp_status_counts['total'] or 0,
        'employees_active': emp_status_counts['active'] or 0,
        'employees_leave': emp_status_counts['leave'] or 0,
        'employees_suspended': emp_status_counts['suspended'] or 0,
        'employees_terminated': emp_status_counts['terminated'] or 0,
        'employment_requests_open': er_open_count,
        'pending_actions_open': pa_open_count,
        'branches_count': Branch.objects.filter(is_deleted=False).count() if request.user.is_superuser else len(accessible_branch_ids),
    }

    context = {
        'stats': stats,
        'branch_distribution': branch_distribution,
        'max_branch': max_branch,
        'show_overview': bool(request.user.is_superuser or _is_general_manager(request.user)),
        'is_branch_manager': False,
        'pending_requests': [],
        'is_hr_officer': False,
        'officer_employment_requests': [],
        'officer_pending_actions': [],
        'is_general_manager': False,
        'gm_employment_requests': [],
        'gm_pending_actions': [],
        'hr_officers': [],
    }

    # طلبات التوظيف المعلقة الخاصة بفروع المستخدم (لمدير الفرع / السوبر)
    if request.user.is_superuser or request.user.managed_branches.filter(is_deleted=False).exists():
        context['is_branch_manager'] = True
        qs = EmploymentRequest.objects.select_related(
            'branch', 'department', 'cost_center', 'requested_by'
        ).filter(status__in=[
            EmploymentRequest.Status.PENDING,
            EmploymentRequest.Status.PENDING_BRANCH,
        ])
        if not request.user.is_superuser:
            managed = list(request.user.managed_branches.values_list('id', flat=True))
            qs = qs.filter(branch_id__in=managed)
        context['pending_requests'] = qs.order_by('-created_at')

    # ─── المهام المُسندة للمستخدم الحالي (أي شخص له تعيينات) ─────────────────
    user_emp_qs = EmploymentRequest.objects.select_related(
        'branch', 'department', 'cost_center', 'requested_by',
    ).filter(
        assigned_officer=request.user,
        status=EmploymentRequest.Status.PENDING_OFFICER,
    )
    user_actions_qs = PendingAction.objects.select_related(
        'employee', 'employee__branch', 'requested_by',
    ).filter(
        assigned_officer=request.user,
        status=PendingAction.Status.PENDING_OFFICER,
    )
    if user_emp_qs.exists() or user_actions_qs.exists() or _is_hr_officer(request.user) or request.user.is_superuser:
        context['is_hr_officer'] = True
        context['officer_employment_requests'] = user_emp_qs.order_by('-assigned_at')
        context['officer_pending_actions'] = user_actions_qs.order_by('-assigned_at')

    # ─── المهام في مرحلة المدير العام / مدير الموارد ────────────────────────
    if _is_general_manager(request.user):
        context['is_general_manager'] = True
        context['hr_officers'] = get_hr_officers()

        gm_emp_qs = EmploymentRequest.objects.select_related(
            'branch', 'department', 'cost_center', 'requested_by',
        ).filter(status=EmploymentRequest.Status.PENDING_GM)
        context['gm_employment_requests'] = gm_emp_qs.order_by('-branch_reviewed_at', '-created_at')

        gm_actions_qs = PendingAction.objects.select_related(
            'employee', 'employee__branch', 'requested_by',
        ).filter(status=PendingAction.Status.PENDING_GM)
        context['gm_pending_actions'] = gm_actions_qs.order_by('-created_at')

    # ─── صندوق المهام الموحَّد (Unified Inbox) ───────────────────────────────
    inbox = []

    def _push_er(req, kind_label, badge, action_url, action_label, action_icon, action_color):
        inbox.append({
            'type': kind_label,
            'badge': badge,
            'title': req.name or '—',
            'subtitle': f"{(req.branch.name if req.branch_id else '—')} • {(req.department.name if req.department_id else '—')}",
            'date': req.assigned_at or req.created_at,
            'action_url': action_url,
            'action_label': action_label,
            'action_icon': action_icon,
            'action_color': action_color,
        })

    def _push_pa(a, badge, action_url, action_label, action_icon, action_color):
        inbox.append({
            'type': a.get_action_type_display(),
            'badge': badge,
            'title': a.employee.name if a.employee_id else '—',
            'subtitle': f"{(a.employee.branch.name if a.employee_id and a.employee.branch_id else '—')}",
            'date': a.assigned_at or a.created_at,
            'action_url': action_url,
            'action_label': action_label,
            'action_icon': action_icon,
            'action_color': action_color,
        })

    for req in context.get('officer_employment_requests') or []:
        _push_er(req, 'طلب توظيف', 'indigo',
                 reverse('web:edit_employment_request', args=[req.id]),
                 'تجهيز واعتماد', 'edit-3', 'indigo')
    for a in context.get('officer_pending_actions') or []:
        _push_pa(a, 'amber',
                 reverse('web:pending_action_detail', args=[a.id]),
                 'تنفيذ', 'play', 'amber')
    for req in context.get('pending_requests') or []:
        _push_er(req, 'طلب توظيف (فرع)', 'amber',
                 reverse('web:list_employment_requests'),
                 'مراجعة', 'eye', 'emerald')
    for req in context.get('gm_employment_requests') or []:
        _push_er(req, 'طلب توظيف (م.عام)', 'blue',
                 reverse('web:list_employment_requests') + '?status=pending_gm',
                 'معالجة', 'eye', 'blue')
    for a in context.get('gm_pending_actions') or []:
        _push_pa(a, 'purple',
                 reverse('web:pending_action_detail', args=[a.id]),
                 'معالجة', 'eye', 'purple')

    # بحث
    q = (request.GET.get('q') or '').strip()
    if q:
        ql = q.lower()
        inbox = [t for t in inbox if ql in (t['title'] or '').lower()
                 or ql in (t['subtitle'] or '').lower()
                 or ql in (t['type'] or '').lower()]

    # ترتيب من الأحدث
    inbox.sort(key=lambda t: t['date'] or 0, reverse=True)

    # ترقيم: 8 صفوف بالصفحة
    paginator = Paginator(inbox, 8)
    page_number = request.GET.get('page') or 1
    page_obj = paginator.get_page(page_number)
    context['inbox_page'] = page_obj
    context['inbox_total'] = len(inbox)
    context['inbox_query'] = q

    return render(request, 'pages/dashboard.html', context)

# =============================================================================
# Dashboard / Employees Tab View
# =============================================================================
