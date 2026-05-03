"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from functools import wraps

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
    from apps.employees.models import EmploymentRequest
    from apps.core.models import PendingAction
    from apps.core.web_views._helpers import _is_hr_officer, _is_general_manager
    from apps.core.web_views.employment_requests import get_hr_officers

    context = {
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

    # ─── المهام المُسندة لأخصائي الموارد ────────────────────────────────────
    if _is_hr_officer(request.user) or request.user.is_superuser:
        context['is_hr_officer'] = True

        # طلبات توظيف مُسندة إليه ولم تُعتمد بعد
        emp_qs = EmploymentRequest.objects.select_related(
            'branch', 'department', 'cost_center', 'requested_by',
        ).filter(
            assigned_officer=request.user,
            status=EmploymentRequest.Status.PENDING_OFFICER,
        )
        context['officer_employment_requests'] = emp_qs.order_by('-assigned_at')

        # عمليات أخرى (إجازات، رواتب...) مُسندة إليه
        actions_qs = PendingAction.objects.select_related(
            'employee', 'employee__branch', 'requested_by',
        ).filter(
            assigned_officer=request.user,
            status=PendingAction.Status.PENDING_OFFICER,
        )
        context['officer_pending_actions'] = actions_qs.order_by('-assigned_at')

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

    return render(request, 'pages/dashboard.html', context)

# =============================================================================
# Dashboard / Employees Tab View
# =============================================================================
