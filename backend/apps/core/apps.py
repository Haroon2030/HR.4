from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_permissions_signal(sender, **kwargs):
    """مزامنة الصلاحيات تلقائياً بعد كل migrate."""
    # مزامنة فقط من تطبيق core (لتفادي التكرار)
    if sender.name != 'apps.core':
        return
    try:
        # تأكد من استيراد كل web_views حتى تُسجَّل decorators
        import apps.core.web_views  # noqa: F401
        from apps.core.permissions_registry import sync_to_db
        modules, perms, new = sync_to_db(verbose=False)
        print(f'[permissions] synced: {modules} modules, {perms} perms ({new} new)')
    except Exception as e:
        # خلال أول migrate، الجداول قد لا تكون موجودة بعد — تجاهل بصمت
        print(f'[permissions] sync skipped: {e}')


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'النظام الأساسي'

    def ready(self):
        """تفعيل الـ signals عند تشغيل التطبيق"""
        from apps.core.employee_tab_permissions import register_employee_tab_permissions
        register_employee_tab_permissions()
        import apps.core.signals  # noqa: F401
        # ربط الـ post_migrate لمزامنة الصلاحيات تلقائياً
        post_migrate.connect(_sync_permissions_signal, sender=self)
