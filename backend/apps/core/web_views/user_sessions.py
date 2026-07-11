"""إدارة جلسات الويب — للأدمن فقط."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.decorators import permission_required
from apps.core.models import UserSession
from apps.core.services.access_control import (
    can_administer_user,
    filter_users_queryset,
)
from apps.core.services.user_sessions import (
    list_active_sessions,
    list_active_sessions_for_users,
    revoke_all_sessions,
    revoke_session_record,
)

User = get_user_model()


def _deny_administration(request, target_user):
    messages.error(request, 'لا تملك صلاحية إدارة جلسات هذا المستخدم.')
    return redirect('web:list_users')


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
    return render(request, 'pages/users/sessions_list.html', {
        'sessions': sessions,
        'current_session_key': current_key,
        'page_title': 'إدارة الجلسات',
    })


@login_required
@permission_required('users.edit')
def list_user_sessions(request, user_id):
    """جلسات مستخدم محدد."""
    target = get_object_or_404(
        User.objects.select_related('profile__role'),
        pk=user_id,
    )
    if not can_administer_user(request.user, target):
        return _deny_administration(request, target)

    sessions = list_active_sessions(target)
    current_key = getattr(request.session, 'session_key', None)
    return render(request, 'pages/users/sessions_user.html', {
        'target_user': target,
        'sessions': sessions,
        'current_session_key': current_key,
        'active_session_count': sessions.count(),
    })


@login_required
@permission_required('users.edit')
@require_http_methods(['POST'])
def revoke_session_view(request, pk):
    """إنهاء جلسة واحدة."""
    record = get_object_or_404(
        UserSession.objects.select_related('user'),
        pk=pk,
        revoked_at__isnull=True,
    )
    if not can_administer_user(request.user, record.user):
        return _deny_administration(request, record.user)

    current_key = getattr(request.session, 'session_key', None)
    if current_key and record.session_key == current_key:
        messages.error(request, 'لا يمكنك إنهاء جلسة المتصفح الحالية من هنا — استخدم تسجيل الخروج.')
        return redirect('web:list_user_sessions', user_id=record.user_id)

    revoke_session_record(record, actor=request.user, request=request)
    messages.success(request, f'تم إنهاء الجلسة ({record.device_label or "جهاز"}) بنجاح.')
    next_url = request.POST.get('next') or ''
    if next_url == 'all':
        return redirect('web:list_all_sessions')
    return redirect('web:list_user_sessions', user_id=record.user_id)


@login_required
@permission_required('users.edit')
@require_http_methods(['POST'])
def revoke_all_user_sessions_view(request, user_id):
    """إنهاء كل جلسات مستخدم."""
    target = get_object_or_404(User, pk=user_id)
    if not can_administer_user(request.user, target):
        return _deny_administration(request, target)

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
        messages.info(request, 'لا توجد جلسات نشطة لإنهائها.')
    return redirect('web:list_user_sessions', user_id=target.pk)
