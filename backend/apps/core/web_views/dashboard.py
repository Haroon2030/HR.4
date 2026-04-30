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

    context = {'is_branch_manager': False, 'pending_requests': []}

    # طلبات التوظيف المعلقة الخاصة بفروع المستخدم (لمدير الفرع / السوبر)
    if request.user.is_superuser or request.user.managed_branches.filter(is_deleted=False).exists():
        context['is_branch_manager'] = True
        qs = EmploymentRequest.objects.select_related(
            'branch', 'department', 'cost_center', 'requested_by'
        ).filter(status=EmploymentRequest.Status.PENDING)
        if not request.user.is_superuser:
            managed = list(request.user.managed_branches.values_list('id', flat=True))
            qs = qs.filter(branch_id__in=managed)
        context['pending_requests'] = qs.order_by('-created_at')

    return render(request, 'pages/dashboard.html', context)

# =============================================================================
# Dashboard / Employees Tab View
# =============================================================================
