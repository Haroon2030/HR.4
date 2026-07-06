from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.maintenance'
    verbose_name = 'إدارة الصيانة'

    def ready(self):
        from apps.core.permissions_registry import register_module, register_permission

        register_module('maintenance', name='إدارة الصيانة', icon='wrench', order=14)
        for code in (
            'maintenance.view',
            'maintenance.add',
            'maintenance.assign',
            'maintenance.manage',
            'maintenance.confirm_branch',
            'maintenance.return',
            'maintenance.workers_view',
            'maintenance.workers_add',
            'maintenance.workers_edit',
            'maintenance.workers_delete',
        ):
            register_permission(code)
