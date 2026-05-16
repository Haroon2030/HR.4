"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from apps.core.forms import ArabicPasswordChangeForm

from apps.core.models import UserProfile

_LOGIN_ATTEMPT_LIMIT = 20
_LOGIN_LOCKOUT_SECONDS = 3600


def _login_throttle_key(request) -> str:
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    if not ip:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
    return f'login_throttle:{ip}'


# =============================================================================
# Custom Decorators
# =============================================================================



def login_view(request):
    """صفحة تسجيل الدخول"""
    from apps.core.forms import LoginForm

    if request.user.is_authenticated:
        return redirect('web:dashboard')
    
    if request.method == 'POST':
        throttle_key = _login_throttle_key(request)
        attempts = cache.get(throttle_key, 0)
        if attempts >= _LOGIN_ATTEMPT_LIMIT:
            messages.error(
                request,
                'تم تجاوز عدد محاولات تسجيل الدخول. حاول مرة أخرى لاحقاً.',
            )
            return render(request, 'auth/login.html')

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
            cache.delete(throttle_key)
            login(request, user)
            if not remember:
                request.session.set_expiry(0)
            messages.success(request, f'مرحباً {user.get_full_name() or user.username}')
            return redirect('web:dashboard')

        cache.set(throttle_key, attempts + 1, _LOGIN_LOCKOUT_SECONDS)
        messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')
    
    return render(request, 'auth/login.html')


def logout_view(request):
    """تسجيل الخروج"""
    logout(request)
    messages.success(request, 'تم تسجيل الخروج بنجاح')
    return redirect('web:auth:login')


@login_required
def password_change_view(request):
    """تغيير كلمة المرور للمستخدم الحالي (واجهة ويب)."""
    if request.method == 'POST':
        form = ArabicPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'تم تغيير كلمة المرور بنجاح.')
            return redirect('web:dashboard')
        for errs in form.errors.values():
            for err in errs:
                messages.error(request, err)
    else:
        form = ArabicPasswordChangeForm(request.user)
    return render(request, 'auth/password_change.html', {'form': form})


# =============================================================================
# Dashboard View
# =============================================================================

