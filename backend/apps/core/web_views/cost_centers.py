"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from functools import wraps

from apps.core.models import Branch
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
@admin_required
def list_cost_centers(request, branch_id=None):
    """عرض قائمة مراكز التكلفة"""
    branch = None
    if branch_id:
        branch = get_object_or_404(Branch, id=branch_id)
        cost_centers = CostCenter.objects.filter(branch=branch, is_deleted=False).order_by('code')
    else:
        cost_centers = CostCenter.objects.filter(is_deleted=False).select_related('branch').order_by('code')
    return render(request, 'pages/cost_centers/list.html', {
        'branch': branch,
        'cost_centers': cost_centers
    })


@login_required
@admin_required
def view_cost_center(request, cost_center_id):
    """عرض تفاصيل مركز تكلفة"""
    cost_center = get_object_or_404(
        CostCenter.objects.select_related('branch'),
        id=cost_center_id
    )
    return render(request, 'pages/cost_centers/detail.html', {'cost_center': cost_center})


@login_required
@admin_required
def add_cost_center(request, branch_id=None):
    """إضافة مركز تكلفة جديد"""
    from apps.core.forms import CostCenterForm
    branch = get_object_or_404(Branch, id=branch_id) if branch_id else None

    if request.method == 'POST':
        form = CostCenterForm(request.POST, branch=branch)
        if form.is_valid():
            cost_center = form.save(commit=False)
            cost_center.branch = branch
            cost_center.is_active = True
            cost_center.save()
            messages.success(request, f'تم إنشاء مركز التكلفة "{cost_center.name}" بنجاح')
            return redirect('web:view_cost_center', cost_center_id=cost_center.id)
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/cost_centers/form.html', {'branch': branch})


@login_required
@admin_required
def edit_cost_center(request, cost_center_id):
    """تعديل مركز تكلفة"""
    from apps.core.forms import CostCenterForm
    cost_center = get_object_or_404(CostCenter, id=cost_center_id)

    if request.method == 'POST':
        form = CostCenterForm(request.POST, instance=cost_center, branch=cost_center.branch)
        if form.is_valid():
            cost_center = form.save()
            messages.success(request, f'تم تحديث مركز التكلفة "{cost_center.name}" بنجاح')
            return redirect('web:view_cost_center', cost_center_id=cost_center.id)
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/cost_centers/form.html', {
        'branch': cost_center.branch,
        'cost_center': cost_center
    })


# =============================================================================
# Departments Views - إدارة الأقسام
# =============================================================================

@login_required
@admin_required
def delete_cost_center(request, cost_center_id):
    """حذف مركز تكلفة (soft delete)"""
    cost_center = get_object_or_404(CostCenter, id=cost_center_id)
    if request.method == 'POST':
        name = cost_center.name
        cost_center.delete()
        messages.success(request, f'تم حذف مركز التكلفة "{name}" بنجاح')
    return redirect('web:list_branches')


