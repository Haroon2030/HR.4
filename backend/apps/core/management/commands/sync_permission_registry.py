"""
مزامنة سجل الصلاحيات (registry) مع AppModule و Permission.
python manage.py sync_permission_registry
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'مزامنة الوحدات والصلاحيات من decorators و register_module'

    def handle(self, *args, **options):
        from apps.core.apps import _sync_permissions_to_db

        self.stdout.write(self.style.WARNING('🔄 مزامنة سجل الصلاحيات...'))
        modules, perms, new = _sync_permissions_to_db(verbose=True)
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ {modules} وحدة، {perms} صلاحية ({new} جديدة)'
            )
        )
