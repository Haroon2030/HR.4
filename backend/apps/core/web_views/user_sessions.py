"""إدارة جلسات الويب — للمستخدم (جلساته) أو للأدمن."""
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.decorators import permission_required
from apps.core.models import UserSession
from apps.core.services.access_control import (
    can_manage_user_sessions,
    filter_users_queryset,
)
from apps.core.services.user_sessions import (
    list_active_sessions,
    list_active_sessions_for_users,
    revoke_all_sessions,
    revoke_session_record,
)

User = get_user_model()

SESSIONS_POLL_INTERVAL = '30s'


def _deny_session_management(request, target_user):
    messages.error(request, 'لا تملك صلاحية إدارة جلسات هذا المستخدم.')
    if request.user.pk == target_user.pk:
        return redirect('web:auth:my_sessions')
    return redirect('web:list_users')


def _sessions_redirect(request, user, *, next_url=''):
    if next_url == 'mine':
        return redirect('web:auth:my_sessions')
    if next_url == 'all':
        return redirect('web:list_all_sessions')
    return redirect('web:list_user_sessions', user_id=user.pk)


def _sessions_panel_context(
    *,
    sessions,
    current_key,
    show_user_column=False,
    revoke_next='',
):
    return {
        'sessions': sessions,
        'current_session_key': current_key,
        'active_session_count': sessions.count() if hasattr(sessions, 'count') else len(sessions),
        'show_user_column': show_user_column,
        'revoke_next': revoke_next,
    }


def _render_sessions_panel(request, context):
    return render(request, 'pages/users/_sessions_panel.html', context)


def _respond_sessions_page(request, *, page_template, page_context):
    if request.headers.get('HX-Request'):
        panel_keys = (
            'sessions', 'current_session_key', 'active_session_count',
            'show_user_column', 'revoke_next',
        )
        return _render_sessions_panel(request, {k: page_context[k] for k in panel_keys})
    return render(request, page_template, page_context)


@login_required
def my_sessions(request):
    """جلسات المتصفح النشطة للمستخدم الحالي."""
    sessions = list_active_sessions(request.user)
    current_key = getattr(request.session, 'session_key', None)
    context = {
        **_sessions_panel_context(
            sessions=sessions,
            current_key=current_key,
            revoke_next='mine',
        ),
        'page_title': 'جلساتي',
        'poll_interval': SESSIONS_POLL_INTERVAL,
    }
    return _respond_sessions_page(request, page_template='pages/users/sessions_my.html', page_context=context)


@login_required
@permission_required('users.edit')
def list_all_sessions(request):
    """كل الجلسات النشطة ضمن نطاق المستخدمين المتاح للأدمن."""
    accessible_users = filter_users_queryset(
        request.user,
        User.objects.filter(is_active=True),
    )
    user_ids = list(accessible_users.values_list('pk', flat=True))
    sessions = list_active_sessions_for_users(user_ids)
    current_key = getattr(request.session, 'session_key', None)
    context = {
        **_sessions_panel_context(
            sessions=sessions,
            current_key=current_key,
            show_user_column=True,
            revoke_next='all',
        ),
        'page_title': 'إدارة الجلسات',
        'poll_interval': SESSIONS_POLL_INTERVAL,
    }
    return _respond_sessions_page(request, page_template='pages/users/sessions_list.html', page_context=context)


@login_required
def list_user_sessions(request, user_id):
    """جلسات مستخدم محدد — للأدمن أو للمستخدم نفسه."""
    target = get_object_or_404(
        User.objects.select_related('profile__role'),
        pk=user_id,
    )
    if not can_manage_user_sessions(request.user, target):
        return _deny_session_management(request, target)

    sessions = list_active_sessions(target)
    current_key = getattr(request.session, 'session_key', None)
    is_self = request.user.pk == target.pk
    context = {
        **_sessions_panel_context(
            sessions=sessions,
            current_key=current_key,
            revoke_next='mine' if is_self else '',
        ),
        'target_user': target,
        'is_self_sessions': is_self,
        'poll_interval': SESSIONS_POLL_INTERVAL,
    }
    return _respond_sessions_page(request, page_template='pages/users/sessions_user.html', page_context=context)


@login_required
@require_http_methods(['POST'])
def revoke_session_view(request, pk):
    """إنهاء جلسة واحدة."""
    record = get_object_or_404(
        UserSession.objects.select_related('user'),
        pk=pk,
        revoked_at__isnull=True,
    )
    if not can_manage_user_sessions(request.user, record.user):
        return _deny_session_management(request, record.user)

    current_key = getattr(request.session, 'session_key', None)
    is_current = bool(current_key and record.session_key == current_key)

    revoke_session_record(record, actor=request.user, request=request)
    next_url = request.POST.get('next') or ''

    if is_current:
        logout(request)
        messages.success(request, 'تم إنهاء جلسة المتصفح الحالية. يُرجى تسجيل الدخول مجدداً.')
        return redirect('web:auth:login')

    messages.success(request, f'تم إنهاء الجلسة ({record.device_label or "جهاز"}) بنجاح.')
    if request.headers.get('HX-Request'):
        return _respond_sessions_page_after_revoke(request, record.user, next_url=next_url)
    return _sessions_redirect(request, record.user, next_url=next_url)


def _respond_sessions_page_after_revoke(request, user, *, next_url=''):
    """تحديث لوحة الجلسات بعد إنهاء جلسة (بدون إعادة تحميل كاملة)."""
    if next_url == 'all':
        return list_all_sessions(request)
    if next_url == 'mine' or request.user.pk == user.pk:
        return my_sessions(request)
    return list_user_sessions(request, user_id=user.pk)


@login_required
@require_http_methods(['POST'])
def revoke_all_user_sessions_view(request, user_id):
    """إنهاء كل جلسات مستخدم."""
    target = get_object_or_404(User, pk=user_id)
    if not can_manage_user_sessions(request.user, target):
        return _deny_session_management(request, target)

    except_key = None
    if target.pk == request.user.pk:
        except_key = getattr(request.session, 'session_key', None)

    count = revoke_all_sessions(
        target,
        actor=request.user,
        request=request,
        except_session_key=except_key,
    )
    if count:
        messages.success(request, f'تم إنهاء {count} جلسة نشطة.')
    else:
        messages.info(request, 'لا توجد جلسات أخرى لإنهائها.')
    next_url = request.POST.get('next') or ''
    if request.headers.get('HX-Request'):
        return _respond_sessions_page_after_revoke(request, target, next_url=next_url)
    if next_url == 'mine':
        return redirect('web:auth:my_sessions')
    return redirect('web:list_user_sessions', user_id=target.pk)
