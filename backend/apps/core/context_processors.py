"""
معالجات سياق القوالب — Context Processors
==========================================
تُنفَّذ على كل صفحة مسجّلة. العدادات تُخزَّن مؤقتاً (انظر sidebar_counts.py).
"""
import logging

logger = logging.getLogger(__name__)


def sidebar_context(request):
    """
    عدادات الشريط الجانبي والإشعارات (مخزّنة مؤقتاً ~45 ثانية).

    المتغيرات:
      - pending_actions_count
      - pending_for_me_count
      - unread_notifications_count
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    from apps.core.services.sidebar_counts import get_sidebar_counts

    return get_sidebar_counts(user)


# توافق مع الإصدارات السابقة — تستدعي نفس الذاكرة المؤقتة
def pending_actions_count(request):
    data = sidebar_context(request)
    if not data:
        return {}
    return {'pending_actions_count': data.get('pending_actions_count', 0)}


def approval_inbox(request):
    data = sidebar_context(request)
    if not data:
        return {}
    return {
        'pending_for_me_count': data.get('pending_for_me_count', 0),
        'unread_notifications_count': data.get('unread_notifications_count', 0),
    }
