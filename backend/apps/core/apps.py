from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _import_permission_registry():
    """استيراد كل الـ views المحمية لتسجيل الصلاحيات في الـ registry."""
    import apps.core.web_views  # noqa: F401
    import apps.payroll.views  # noqa: F401


def _sync_permissions_to_db(verbose=False):
    from apps.core.permissions_registry import sync_to_db

    _import_permission_registry()
    return sync_to_db(verbose=verbose)


def _sync_permissions_signal(sender, **kwargs):
    """مزامنة الصلاحيات تلقائياً بعد كل migrate."""
    if sender.name != 'apps.core':
        return
    try:
        modules, perms, new = _sync_permissions_to_db(verbose=False)
        print(f'[permissions] synced: {modules} modules, {perms} perms ({new} new)')
    except Exception as e:
        print(f'[permissions] sync skipped: {e}')


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'النظام الأساسي'

    def ready(self):
        """تفعيل الـ signals عند تشغيل التطبيق"""
        from apps.core.employee_tab_permissions import register_employee_tab_permissions
        from apps.core.permissions_registry import register_module, register_permission

        register_module('cash_shortages', name='عجز الكاشير', icon='banknote', order=13)
        register_permission('cash_shortages.view')
        register_permission('cash_shortages.add')
        register_employee_tab_permissions()
        import apps.core.signals  # noqa: F401
        post_migrate.connect(_sync_permissions_signal, sender=self)
