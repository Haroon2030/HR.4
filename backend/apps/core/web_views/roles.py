"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from functools import wraps

from apps.core.models import Role
from apps.core.forms import RoleForm
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
def list_roles(request):
    """قائمة الأدوار"""
    roles = Role.objects.all().prefetch_related('users')
    return render(request, 'pages/roles/list.html', {'roles': roles})

@login_required
@admin_required
def view_role(request, role_id):
    """عرض تفاصيل دور معين"""
    from django.shortcuts import get_object_or_404
    role = get_object_or_404(Role, id=role_id)
    return render(request, 'pages/roles/detail.html', {'role': role})

@login_required
@admin_required
def edit_role(request, role_id):
    """تعديل دور"""
    from django.shortcuts import get_object_or_404
    
    role = get_object_or_404(Role, id=role_id)
    
    if request.method == 'POST':
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'تم تحديث الدور "{role.name}" بنجاح')
            return redirect('web:list_roles')
        for err in form.errors.values():
            messages.error(request, err[0])
    
    return render(request, 'pages/roles/form.html', {
        'role': role
    })

@login_required
@admin_required
def add_role(request):
    """إضافة دور جديد"""
    
    if request.method == 'POST':
        form = RoleForm(request.POST)
        if form.is_valid():
            role = form.save(commit=False)
            role.is_system_role = False
            role.save()
            messages.success(request, f'تم إنشاء الدور "{role.name}" بنجاح')
            return redirect('web:list_roles')
        for err in form.errors.values():
            messages.error(request, err[0])
    
    return render(request, 'pages/roles/form.html')


# =============================================================================
# Branches Management
# =============================================================================

