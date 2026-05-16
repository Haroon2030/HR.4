from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.attendance'
    verbose_name = 'الحضور والبصمة'

    def ready(self):
        from apps.core.permissions_registry import register_module
        register_module('attendance', name='الحضور والبصمة', icon='fingerprint', order=11)
