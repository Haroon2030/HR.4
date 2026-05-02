"""
Django Signals للنظام الأساسي
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserProfile, PendingAction

User = get_user_model()


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
def notify_branch_on_pending_action_created(sender, instance, created, **kwargs):
    """عند إنشاء طلب جديد → أبلغ مدير الفرع."""
    if not created:
        return
    try:
        from apps.core.services.pending_actions import notify_branch_on_create
        notify_branch_on_create(instance)
    except Exception:
        # لا نُفشل المعاملة بسبب فشل الإشعار
        pass


def _register_employment_request_signal():
    """تسجيل إشعار إنشاء طلب توظيف (lazy لتجنّب دوّار الاستيراد)."""
    from apps.employees.models import EmploymentRequest

    @receiver(post_save, sender=EmploymentRequest, weak=False,
              dispatch_uid='notify_branch_on_employment_request_created')
    def _notify(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            from apps.core.services.employment_requests import notify_branch_on_create
            notify_branch_on_create(instance)
        except Exception:
            pass


_register_employment_request_signal()
