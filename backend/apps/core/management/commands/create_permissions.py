"""
مزامنة الصلاحيات من الـ registry (المُعبَّأ تلقائياً من decorators على الـ views).

الاستخدام:
    python manage.py create_permissions

ملاحظة: تتم المزامنة تلقائياً بعد كل migrate أيضاً.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'مزامنة الوحدات والصلاحيات من registry تلقائياً، ومنح الأدمن جميع الصلاحيات'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('🔄 مزامنة الوحدات والصلاحيات...'))

        # التأكد من تحميل كل views (يُشغّل decorators ويملأ الـ registry)
        import apps.core.web_views  # noqa: F401

        from apps.core.permissions_registry import sync_to_db, get_registry

        registry = get_registry()
        for code, entry in sorted(registry.items(), key=lambda kv: kv[1].get('order', 100)):
            ops = ', '.join(sorted(entry['operations']))
            self.stdout.write(f"  📦 {entry.get('name', code)} ({code}) → [{ops}]")

        modules, perms, new = sync_to_db(verbose=False)

        self.stdout.write(self.style.SUCCESS(
            f'✅ {modules} وحدة · {perms} صلاحية · {new} جديدة'
        ))

        from apps.core.models import Role
        admin_count = Role.objects.filter(role_type=Role.RoleType.ADMIN).count()
        if admin_count:
            self.stdout.write(self.style.SUCCESS(f'👑 الأدمن ({admin_count}): يمتلك جميع الصلاحيات'))

        self.stdout.write(self.style.SUCCESS('🎉 تم بنجاح'))
