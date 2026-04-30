from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'النظام الأساسي'
    
    def ready(self):
        """تفعيل الـ signals عند تشغيل التطبيق"""
        import apps.core.signals
