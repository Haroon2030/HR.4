from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payroll'
    verbose_name = 'مسير الرواتب'

    def ready(self):
        from apps.core.permissions_registry import register_module, register_permission

        register_module(
            'payroll',
            name='مسير الرواتب',
            icon='calculator',
            order=9,
        )
        for code in ('view', 'manage', 'process', 'view_reports'):
            register_permission(f'payroll.{code}')
