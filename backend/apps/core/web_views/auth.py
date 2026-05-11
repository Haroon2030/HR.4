"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.core.models import UserProfile
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.web_views._helpers import (
    admin_required, _is_branch_manager, branch_manager_required,
    _user_accessible_branch_ids, employee_branch_access_required, _can_review_action,
)

def login_view(request):
    """صفحة تسجيل الدخول"""
    from apps.core.forms import LoginForm

    if request.user.is_authenticated:
        return redirect('web:dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, err[0])
            return render(request, 'auth/login.html')

        cd = form.cleaned_data
        username = cd['username']
        password = cd['password']
        remember = cd.get('remember')

        user = authenticate(request, username=username, password=password)
        if user is None and username:
            try:
                profile = UserProfile.objects.select_related('user').get(user_number=username)
                user = authenticate(request, username=profile.user.username, password=password)
            except UserProfile.DoesNotExist:
                pass
        
        if user is not None:
            login(request, user)
            if not remember:
                request.session.set_expiry(0)
            messages.success(request, f'مرحباً {user.get_full_name() or user.username}')
            return redirect('web:dashboard')
        else:
            messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')
    
    return render(request, 'auth/login.html')


def logout_view(request):
    """تسجيل الخروج"""
    logout(request)
    messages.success(request, 'تم تسجيل الخروج بنجاح')
    return redirect('web:auth:login')


# =============================================================================
# Dashboard View
# =============================================================================

