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
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


# =============================================================================
# Custom Decorators
# =============================================================================

def admin_required(view_func):
    """تحقق من أن المستخدم لديه دور أدمن"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web:auth:login')
        
        # السماح لـ superuser بالدخول مباشرة
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # التحقق من دور الأدمن عبر الـ Profile
        try:
            user_profile = request.user.profile
            if user_profile.role and user_profile.role.role_type == Role.RoleType.ADMIN:
                return view_func(request, *args, **kwargs)
        except Exception as e:
            # لا يوجد profile للمستخدم
            pass
        
        messages.error(request, 'ليس لديك صلاحية للوصول إلى هذه الصفحة')
        return redirect('web:dashboard')
    return wrapper


# =============================================================================
# Authentication Views
# =============================================================================

def _is_branch_manager(user):
    """هل المستخدم مدير فرع؟ (يدير فرعاً واحداً على الأقل)"""
    return user.is_superuser or user.managed_branches.filter(is_deleted=False).exists()


def branch_manager_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web:auth:login')
        if _is_branch_manager(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'هذه الصفحة متاحة لمدراء الفروع فقط')
        return redirect('web:dashboard')
    return wrapper


def _user_accessible_branch_ids(user):
    """قائمة الفروع التي يحقّ للمستخدم العمل عليها (admin/superuser = الكل)."""
    if user.is_superuser:
        return None  # أي فرع
    profile = getattr(user, 'profile', None)
    if profile and profile.role and profile.role.role_type == Role.RoleType.ADMIN:
        return None
    ids = set(user.managed_branches.values_list('id', flat=True))
    if profile:
        if profile.branch_id:
            ids.add(profile.branch_id)
        ids.update(profile.assigned_branches.values_list('id', flat=True))
    return ids


def employee_branch_access_required(view_func):
    """يمنع الوصول للموظف ما لم يكن المستخدم admin/مدير الفرع/أخصائي الفرع."""
    @wraps(view_func)
    def wrapper(request, employee_id, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web:auth:login')
        from apps.employees.models import Employee
        employee = get_object_or_404(Employee, id=employee_id)
        accessible = _user_accessible_branch_ids(request.user)
        if accessible is not None and employee.branch_id not in accessible:
            messages.error(request, 'لا تملك صلاحية على فرع هذا الموظف.')
            return redirect('web:list_employees')
        return view_func(request, employee_id, *args, **kwargs)
    return wrapper


def _can_review_action(user, action):
    """يحدّد ما إذا كان المستخدم يستطيع الموافقة/الرفض على هذا الطلب."""
    if user.is_superuser:
        return True
    if action.branch_id and action.branch_id in list(
        user.managed_branches.values_list('id', flat=True)
    ):
        return True
    return False


