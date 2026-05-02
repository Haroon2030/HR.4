"""خدمة الإشعارات الداخلية (الجرس)."""
from django.urls import reverse, NoReverseMatch

from apps.core.models import Notification


def notify(recipient, *, title, message='', link='', icon='bell',
           color=Notification.Color.PRIMARY, related_action=None):
    """ينشئ إشعاراً للمستخدم. يتجاهل الـ recipient الفارغ بصمت."""
    if not recipient or not getattr(recipient, 'is_authenticated', True):
        return None
    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message or '',
        link=link or '',
        icon=icon or 'bell',
        color=color,
        related_action=related_action,
    )


def notify_action_url(action):
    """يُرجع رابط صفحة تفاصيل الطلب (آمن إذا لم يُسجَّل المسار بعد)."""
    try:
        return reverse('web:pending_action_detail', kwargs={'action_id': action.id})
    except NoReverseMatch:
        try:
            return reverse('web:list_pending_actions')
        except NoReverseMatch:
            return ''


def notify_branch_managers(action, *, title, message='', icon='inbox',
                           color=Notification.Color.PRIMARY):
    """إشعار جميع مدراء الفرع المسؤولين عن الطلب."""
    if not action.branch_id:
        return
    link = notify_action_url(action)
    branch = action.branch
    manager = getattr(branch, 'manager', None)
    if manager:
        notify(manager, title=title, message=message, link=link,
               icon=icon, color=color, related_action=action)


def notify_general_managers(action, *, title, message='', icon='inbox',
                            color=Notification.Color.AMBER):
    """إشعار كل من له دور admin / hr_manager (المدراء العامون)."""
    from django.contrib.auth import get_user_model
    from apps.core.models import Role

    User = get_user_model()
    qs = User.objects.filter(
        is_active=True,
        profile__role__role_type__in=[Role.RoleType.ADMIN, Role.RoleType.HR_MANAGER],
    ).distinct()

    link = notify_action_url(action)
    for user in qs:
        notify(user, title=title, message=message, link=link,
               icon=icon, color=color, related_action=action)


def notify_user(user, action, *, title, message='', icon='inbox',
                color=Notification.Color.INDIGO):
    """إشعار مستخدم محدّد (موظف الموارد المُسند مثلاً)."""
    notify(user, title=title, message=message,
           link=notify_action_url(action),
           icon=icon, color=color, related_action=action)
