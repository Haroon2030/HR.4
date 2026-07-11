"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from apps.core.forms import ArabicPasswordChangeForm
from apps.core.rate_limit import limit_password_change, limit_web_login

from apps.core.models import UserProfile

_RATE_LIMIT_MESSAGE = 'تم تجاوز عدد محاولات تسجيل الدخول. حاول مرة أخرى لاحقاً.'
_PASSWORD_RATE_LIMIT_MESSAGE = 'تجاوزت عدد محاولات تغيير كلمة المرور. حاول لاحقاً.'


def _clear_idle_timeout_messages(request) -> None:
    """إزالة رسائل انتهاء الجلسة القديمة — لا تُعرض بعد تسجيل دخول ناجح."""
    storage = messages.get_messages(request)
    for message in storage:
        if 'بدون نشاط' in str(message):
            continue
        extra_tags = getattr(message, 'extra_tags', '') or ''
        messages.add_message(request, message.level, message.message, extra_tags=extra_tags)


def _login_page_context(request, *, form=None):
    from apps.core.services.user_sessions import idle_timeout_message

    ctx = {
        'idle_expired': request.GET.get('idle') == '1',
        'idle_timeout_message': idle_timeout_message(),
    }
    if form is not None:
        ctx['form'] = form
    return ctx


# =============================================================================
# Custom Decorators
# =============================================================================



@limit_web_login
def login_view(request):
    """صفحة تسجيل الدخول"""
    from apps.core.forms import LoginForm

    if request.user.is_authenticated:
        return redirect('web:dashboard')

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, _RATE_LIMIT_MESSAGE)
            return render(request, 'auth/login.html', _login_page_context(request))

        form = LoginForm(request.POST)

        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, err[0])
            return render(request, 'auth/login.html', _login_page_context(request, form=form))

        cd = form.cleaned_data
        username = cd['username']
        password = cd['password']

        user = authenticate(request, username=username, password=password)
        if user is None and username:
            try:
                profile = UserProfile.objects.select_related('user').get(user_number=username)
                user = authenticate(request, username=profile.user.username, password=password)
            except UserProfile.DoesNotExist:
                pass

        if user is not None:
            from apps.core.services.navigation_cache import invalidate_user_navigation_caches

            invalidate_user_navigation_caches(user.pk)
            login(request, user)
            from apps.core.services.user_sessions import apply_session_idle_expiry, register_session

            register_session(request, user)
            from apps.core.models import SystemAuditLog
            from apps.core.services.system_audit import log_system_audit
            from apps.core.services.user_sessions import parse_device_label

            apply_session_idle_expiry(request)
            ua = (request.META.get('HTTP_USER_AGENT') or '')[:256]
            log_system_audit(
                request=request,
                action=SystemAuditLog.Action.USER_LOGIN,
                summary=f'تسجيل دخول — {user.get_username()}',
                details=f'جهاز: {parse_device_label(ua)}',
                target_user=user,
            )
            display_name = user.get_full_name() or user.username
            _clear_idle_timeout_messages(request)
            messages.add_message(
                request,
                messages.SUCCESS,
                display_name,
                extra_tags='welcome',
            )
            return redirect('web:dashboard')

        messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')

    return render(request, 'auth/login.html', _login_page_context(request))


@require_http_methods(['POST'])
def idle_logout_view(request):
    """تسجيل خروج تلقائي — خمول المتصفح."""
    if not request.user.is_authenticated:
        return redirect('web:auth:login')
    from apps.core.services.user_sessions import revoke_session_by_key

    session_key = getattr(request.session, 'session_key', None)
    if session_key:
        revoke_session_by_key(session_key, actor=request.user, request=request, log=False)
    logout(request)
    return redirect('web:auth:login?idle=1')


@require_http_methods(['GET', 'POST'])
def logout_view(request):
    """تسجيل الخروج — POST فقط (يمنع CSRF logout عبر GET)."""
    if request.method != 'POST':
        return redirect('web:dashboard')
    if not request.user.is_authenticated:
        return redirect('web:auth:login')
    from apps.core.services.user_sessions import revoke_session_by_key

    session_key = getattr(request.session, 'session_key', None)
    if session_key:
        revoke_session_by_key(session_key, actor=request.user, request=request, log=False)
    logout(request)
    messages.success(request, 'تم تسجيل الخروج بنجاح')
    return redirect('web:auth:login')


@login_required
@limit_password_change
def password_change_view(request):
    """تغيير كلمة المرور للمستخدم الحالي (واجهة ويب)."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, _PASSWORD_RATE_LIMIT_MESSAGE)
            form = ArabicPasswordChangeForm(request.user, request.POST)
            return render(request, 'auth/password_change.html', {'form': form})
        form = ArabicPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            from apps.core.models import SystemAuditLog
            from apps.core.services.system_audit import log_system_audit

            log_system_audit(
                request=request,
                action=SystemAuditLog.Action.PASSWORD_CHANGE_SELF,
                summary='تغيير كلمة المرور',
                details=(
                    f'المستخدم «{user.get_username()}» غيّر كلمة مرور حسابه عبر واجهة الويب. '
                    'تم تحديث hash كلمة المرور في جدول auth_user (القيمة غير مخزنة بنص صريح).'
                ),
                target_user=user,
            )
            from apps.core.services.user_sessions import revoke_all_sessions

            current_key = getattr(request.session, 'session_key', None)
            revoked = revoke_all_sessions(
                user,
                actor=user,
                request=request,
                except_session_key=current_key,
            )
            if revoked:
                messages.info(request, f'تم إنهاء {revoked} جلسة أخرى على حسابك.')
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

