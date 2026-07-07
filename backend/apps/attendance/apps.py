from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.attendance'
    verbose_name = 'الحضور والبصمة'

    def ready(self):
        from apps.core.permissions_registry import register_module, register_permission
        from apps.attendance.sub_permissions import register_attendance_sub_permissions

        register_module('attendance', name='الحضور والبصمة', icon='fingerprint', order=11)
        for code in ('attendance.view', 'attendance.manage'):
            register_permission(code)
        register_attendance_sub_permissions()
