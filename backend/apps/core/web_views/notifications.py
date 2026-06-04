"""
Notifications — Views
====================
- list_notifications: صفحة كاملة بالإشعارات
- notifications_dropdown: HTML جزئي للقائمة المنسدلة من رمز الجرس
- read_notification: وضع علامة "مقروء" على إشعار واحد
- read_all_notifications: وضع علامة "مقروء" على الكل
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import Notification


def _user_notifications(user):
    return Notification.objects.filter(recipient=user).select_related('related_action')


@login_required
def list_notifications(request):
    qs = _user_notifications(request.user).order_by('-created_at')[:200]
    return render(request, 'pages/notifications/list.html', {
        'notifications': qs,
        'unread_count': _user_notifications(request.user).filter(is_read=False).count(),
    })


@login_required
def notifications_dropdown(request):
    from django.db.models import Count, Q

    base = _user_notifications(request.user)
    stats = base.aggregate(unread=Count('id', filter=Q(is_read=False)))
    notifications = list(base.order_by('-created_at')[:10])
    return render(request, 'components/notification_dropdown.html', {
        'notifications': notifications,
        'unread_count': stats['unread'] or 0,
    })


@login_required
@require_POST
def read_notification(request, notif_id):
    notif = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    notif.mark_read()
    if request.headers.get('HX-Request'):
        return notifications_dropdown(request)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    if notif.link:
        return redirect(notif.link)
    return redirect('web:list_notifications')


@login_required
@require_POST
def read_all_notifications(request):
    _user_notifications(request.user).filter(is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    if request.headers.get('HX-Request'):
        return notifications_dropdown(request)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('web:list_notifications')


@login_required
@require_POST
def delete_notification(request, notif_id):
    """حذف إشعار واحد."""
    notif = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    notif.delete()
    if request.headers.get('HX-Request'):
        return notifications_dropdown(request)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('web:list_notifications')


@login_required
@require_POST
def delete_all_notifications(request):
    """حذف كل إشعارات المستخدم."""
    _user_notifications(request.user).delete()
    if request.headers.get('HX-Request'):
        return notifications_dropdown(request)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('web:list_notifications')
