"""
Django Signals للنظام الأساسي
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserProfile, PendingAction

User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """إنشاء UserProfile تلقائياً عند إنشاء مستخدم جديد"""
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """حفظ UserProfile عند حفظ المستخدم"""
    try:
        instance.profile.save()
    except UserProfile.DoesNotExist:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=PendingAction)
def invalidate_sidebar_on_pending_action(sender, instance, **kwargs):
    """إبطال عدادات الشريط الجانبي عند تغيير طلب معلّق."""
    from apps.core.services.sidebar_counts import invalidate_sidebar_counts

    invalidate_sidebar_counts(
        instance.requested_by_id,
        instance.assigned_officer_id,
    )


@receiver(post_save, sender=PendingAction)
def notify_branch_on_pending_action_created(sender, instance, created, **kwargs):
    """عند إنشاء طلب جديد → أبلغ مدير الفرع."""
    if not created:
        return
    try:
        from apps.core.services.pending_actions import notify_branch_on_create
        notify_branch_on_create(instance)
    except Exception as e:
        # لا نُفشل المعاملة بسبب فشل الإشعار
        logger.warning("notify_branch_on_pending_action_created failed: %s", e)


def _register_employment_request_signal():
    """تسجيل إشعار إنشاء طلب توظيف (lazy لتجنّب دوّار الاستيراد)."""
    from apps.employees.models import EmploymentRequest

    @receiver(post_save, sender=EmploymentRequest, weak=False,
              dispatch_uid='invalidate_sidebar_on_employment_request')
    def _invalidate_sidebar(sender, instance, **kwargs):
        from apps.core.services.sidebar_counts import invalidate_sidebar_counts

        invalidate_sidebar_counts(
            instance.requested_by_id,
            instance.assigned_officer_id,
        )

    @receiver(post_save, sender=EmploymentRequest, weak=False,
              dispatch_uid='notify_branch_on_employment_request_created')
    def _notify(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            from apps.core.services.employment_requests import notify_branch_on_create
            notify_branch_on_create(instance)
        except Exception as e:
            logger.warning("notify_employment_request signal failed: %s", e)


def _register_notification_signal():
    from apps.core.models import Notification

    @receiver(post_save, sender=Notification, weak=False,
              dispatch_uid='invalidate_sidebar_on_notification')
    def _invalidate_notif(sender, instance, **kwargs):
        from apps.core.services.sidebar_counts import invalidate_sidebar_counts

        invalidate_sidebar_counts(instance.recipient_id)


_register_notification_signal()


_register_employment_request_signal()
