"""
Django Signals للنظام الأساسي
"""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.services.async_dispatch import dispatch_background

from .models import PendingAction, UserProfile

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
    from apps.core.services.navigation_cache import invalidate_user_navigation_caches

    invalidate_user_navigation_caches(
        instance.requested_by_id,
        instance.assigned_officer_id,
    )


def _dispatch_after_commit(task_name: str, fn) -> None:
    """تشغيل الإشعارات بعد commit عند وجود معاملة نشطة."""
    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(lambda: dispatch_background(task_name, fn))
    else:
        dispatch_background(task_name, fn)


@receiver(post_save, sender=PendingAction)
def notify_branch_on_pending_action_created(sender, instance, created, **kwargs):
    """عند إنشاء طلب جديد → أبلغ مدير الفرع (خلفية الطلب لتجنّب حجب POST)."""
    if not created:
        return

    action_id = instance.pk

    def _notify():
        try:
            action = PendingAction.objects.select_related(
                'employee', 'requested_by', 'branch',
            ).get(pk=action_id)
        except PendingAction.DoesNotExist:
            return
        from apps.core.services.pending_actions import notify_branch_on_create

        notify_branch_on_create(action)

    _dispatch_after_commit('pending_action_created_notify', _notify)


def _register_employment_request_signal():
    """تسجيل إشعار إنشاء طلب توظيف (lazy لتجنّب دوّار الاستيراد)."""
    from apps.employees.models import EmploymentRequest

    @receiver(post_save, sender=EmploymentRequest, weak=False,
              dispatch_uid='invalidate_sidebar_on_employment_request')
    def _invalidate_sidebar(sender, instance, **kwargs):
        from apps.core.services.navigation_cache import invalidate_user_navigation_caches

        invalidate_user_navigation_caches(
            instance.requested_by_id,
            instance.assigned_officer_id,
        )

    @receiver(post_save, sender=EmploymentRequest, weak=False,
              dispatch_uid='notify_branch_on_employment_request_created')
    def _notify(sender, instance, created, **kwargs):
        if not created:
            return

        request_id = instance.pk

        def _notify_created():
            try:
                req = EmploymentRequest.objects.select_related(
                    'branch', 'requested_by',
                ).get(pk=request_id)
            except EmploymentRequest.DoesNotExist:
                return
            from apps.core.services.employment_requests import notify_branch_on_create

            notify_branch_on_create(req)

        _dispatch_after_commit('employment_request_created_notify', _notify_created)


def _register_notification_signal():
    from apps.core.models import Notification

    @receiver(post_save, sender=Notification, weak=False,
              dispatch_uid='invalidate_sidebar_on_notification')
    def _invalidate_notif(sender, instance, **kwargs):
        from apps.core.services.navigation_cache import invalidate_user_navigation_caches

        invalidate_user_navigation_caches(instance.recipient_id)


_register_notification_signal()


_register_employment_request_signal()
