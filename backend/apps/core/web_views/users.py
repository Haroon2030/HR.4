"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from functools import wraps

from apps.core.models import Role, Branch, UserProfile
from apps.core.forms import UserCreateForm, UserEditForm
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
def list_users(request):
    """قائمة المستخدمين والأدوار"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.select_related('profile__role', 'profile__branch').all()
    roles = Role.objects.all().prefetch_related('users')
    return render(request, 'pages/users/list.html', {
        'users': users,
        'roles': roles
    })

@login_required
@admin_required
def view_user(request, user_id):
    """عرض تفاصيل مستخدم معين"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = get_object_or_404(User.objects.select_related('profile__role', 'profile__branch'), id=user_id)
    return render(request, 'pages/users/detail.html', {'user_obj': user})


@login_required
@admin_required
def delete_user(request, user_id):
    """حذف مستخدم (للأدمن فقط)"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = get_object_or_404(User, id=user_id)

    # منع حذف الذات
    if user.id == request.user.id:
        messages.error(request, 'لا يمكنك حذف حسابك الخاص')
        return redirect('web:list_users')

    # منع حذف المستخدمين المحميين
    profile = getattr(user, 'profile', None)
    if profile and getattr(profile, 'is_protected', False):
        messages.error(request, f'لا يمكن حذف المستخدم المحمي "{user.username}"')
        return redirect('web:list_users')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'تم حذف المستخدم "{username}" بنجاح')
        return redirect('web:list_users')

    return redirect('web:list_users')

@login_required
@admin_required
def edit_user(request, user_id):
    """تعديل مستخدم"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    user = get_object_or_404(User, id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    roles = Role.objects.filter(is_active=True)
    branches = Branch.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, err[0])
            return render(request, 'pages/users/form.html', {
                'user_obj': user, 'roles': roles, 'branches': branches
            })
        cd = form.cleaned_data

        # تحديث بيانات المستخدم الأساسية
        user.username = cd['username']
        user.first_name = cd.get('first_name', '') or user.first_name
        user.last_name = cd.get('last_name', '') or user.last_name
        user.email = cd.get('email', '') or user.email
        if cd.get('is_active') is not None:
            user.is_active = cd['is_active']
        
        # تحديث كلمة المرور إذا تم إدخالها
        password = cd.get('password')
        if password:
            user.set_password(password)
        
        user.save()
        
        # تحديث البروفايل
        profile.role = cd.get('role')
        profile.branch = cd.get('branch')
        profile.user_number = cd.get('user_number')
        profile.phone = cd.get('phone', '')
        profile.position = cd.get('position', '')
        profile.save()
        
        # تحديث الفروع المكلف بها (للأخصائيين)
        assigned_branches = cd.get('assigned_branches')
        if profile.role and profile.role.role_type == 'specialist':
            profile.assigned_branches.set(assigned_branches or [])
        else:
            profile.assigned_branches.clear()
        
        messages.success(request, f'تم تحديث المستخدم "{user.username}" بنجاح')
        return redirect('web:view_user', user_id=user.id)
    
    return render(request, 'pages/users/form.html', {
        'user_obj': user,
        'roles': roles,
        'branches': branches
    })

@login_required
@admin_required
def add_user(request):
    """إضافة مستخدم جديد"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    roles = Role.objects.filter(is_active=True)
    branches = Branch.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, err[0])
            return render(request, 'pages/users/form.html', {
                'roles': roles, 'branches': branches
            })
        cd = form.cleaned_data
        is_active = cd.get('is_active')
        if is_active is None:
            is_active = True
        
        user = User.objects.create_user(
            username=cd['username'],
            email=cd.get('email', '') or '',
            password=cd['password'],
            first_name=cd.get('first_name', '') or '',
            last_name=cd.get('last_name', '') or '',
            is_active=is_active,
        )
        
        # إنشاء البروفايل
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = cd.get('role')
        profile.branch = cd.get('branch')
        profile.user_number = cd.get('user_number')
        profile.phone = cd.get('phone', '')
        profile.position = cd.get('position', '')
        profile.save()
        
        # تحديث الفروع المكلف بها (للأخصائيين)
        assigned_branches = cd.get('assigned_branches')
        if profile.role and profile.role.role_type == 'specialist' and assigned_branches:
            profile.assigned_branches.set(assigned_branches)
        
        messages.success(request, f'تم إنشاء المستخدم "{user.username}" بنجاح')
        return redirect('web:view_user', user_id=user.id)
    
    return render(request, 'pages/users/form.html', {
        'roles': roles,
        'branches': branches
    })


# =============================================================================
# Cost Centers Views - إدارة مراكز التكلفة
# =============================================================================

