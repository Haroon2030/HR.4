"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from apps.cost_centers.models import CostCenter


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.decorators import permission_required
from apps.core.web_views._branch_scoped import (
    branch_for_scoped_view,
    deny_branch_resource,
    list_branch_scoped_queryset,
    require_branch_access,
)


def _deny_cost_center_branch(request, *, action: str):
    return deny_branch_resource(request, resource_label='مراكز التكلفة', action=action)


@login_required
@permission_required('cost_centers.view')
def list_cost_centers(request, branch_id=None):
    """عرض قائمة مراكز التكلفة"""
    branch, cost_centers, denied = list_branch_scoped_queryset(
        request,
        branch_id,
        resource_label='مراكز التكلفة',
        all_queryset=CostCenter.objects.filter(is_deleted=False).select_related('branch'),
        branch_filter=lambda b: CostCenter.objects.filter(
            branch=b, is_deleted=False,
        ).order_by('code'),
    )
    if denied:
        return denied
    return render(request, 'pages/cost_centers/list.html', {
        'branch': branch,
        'cost_centers': cost_centers
    })


@login_required
@permission_required('cost_centers.view')
def view_cost_center(request, cost_center_id):
    """عرض تفاصيل مركز تكلفة"""
    cost_center = get_object_or_404(
        CostCenter.objects.select_related('branch'),
        id=cost_center_id
    )
    denied = require_branch_access(
        request, cost_center.branch_id, resource_label='مراكز التكلفة', action='عرض',
    )
    if denied:
        return denied
    return render(request, 'pages/cost_centers/detail.html', {'cost_center': cost_center})


@login_required
@permission_required('cost_centers.add')
def add_cost_center(request, branch_id=None):
    """إضافة مركز تكلفة جديد"""
    from apps.core.forms import CostCenterForm
    branch, denied = branch_for_scoped_view(
        request, branch_id, resource_label='مراكز التكلفة', action='إضافة',
    )
    if denied:
        return denied

    if request.method == 'POST':
        form = CostCenterForm(request.POST, branch=branch)
        if form.is_valid():
            cost_center = form.save(commit=False)
            cost_center.branch = branch
            cost_center.is_active = True
            cost_center.save()
            messages.success(request, f'تم إنشاء مركز التكلفة "{cost_center.name}" بنجاح')
            return redirect(reverse('web:list_branches') + '#cost_centers')
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/cost_centers/form.html', {'branch': branch})


@login_required
@permission_required('cost_centers.edit')
def edit_cost_center(request, cost_center_id):
    """تعديل مركز تكلفة"""
    from apps.core.forms import CostCenterForm
    cost_center = get_object_or_404(CostCenter, id=cost_center_id)
    denied = require_branch_access(
        request, cost_center.branch_id, resource_label='مراكز التكلفة', action='تعديل',
    )
    if denied:
        return denied

    if request.method == 'POST':
        form = CostCenterForm(request.POST, instance=cost_center, branch=cost_center.branch)
        if form.is_valid():
            cost_center = form.save()
            messages.success(request, f'تم تحديث مركز التكلفة "{cost_center.name}" بنجاح')
            return redirect(reverse('web:list_branches') + '#cost_centers')
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
@permission_required('cost_centers.delete')
def delete_cost_center(request, cost_center_id):
    """حذف مركز تكلفة (soft delete)"""
    cost_center = get_object_or_404(CostCenter, id=cost_center_id)
    denied = require_branch_access(
        request, cost_center.branch_id, resource_label='مراكز التكلفة', action='حذف',
    )
    if denied:
        return denied
    if request.method == 'POST':
        name = cost_center.name
        cost_center.delete()
        messages.success(request, f'تم حذف مركز التكلفة "{name}" بنجاح')
    return redirect('web:list_branches')

