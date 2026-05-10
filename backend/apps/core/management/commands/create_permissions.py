"""
إنشاء/مزامنة الصلاحيات الأساسية للنظام
- 5 وحدات: employees, branches, departments, users, reports
- 4 عمليات: view, add, edit, delete  (reports: view فقط)
- Admin يحصل تلقائياً على جميع الصلاحيات
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import AppModule, Permission, Role


# تعريف الوحدات
MODULES = [
    {'code': 'employees',   'name': 'الموظفين',           'icon': 'users',         'order': 1},
    {'code': 'branches',    'name': 'الفروع',             'icon': 'building-2',    'order': 2},
    {'code': 'departments', 'name': 'الأقسام',            'icon': 'network',       'order': 3},
    {'code': 'users',       'name': 'المستخدمين والأدوار', 'icon': 'shield-check',  'order': 4},
    {'code': 'reports',     'name': 'التقارير',           'icon': 'bar-chart-3',   'order': 5},
]

# العمليات لكل وحدة
DEFAULT_OPERATIONS = ['view', 'add', 'edit', 'delete']
MODULE_OPERATIONS = {
    'reports': ['view'],   # التقارير: عرض فقط
}

OPERATION_NAMES = {
    'view':   'عرض',
    'add':    'إضافة',
    'edit':   'تعديل',
    'delete': 'حذف',
}


class Command(BaseCommand):
    help = 'إنشاء/مزامنة الوحدات والصلاحيات الأساسية، ومنح الأدمن جميع الصلاحيات'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('🔄 مزامنة الوحدات والصلاحيات...'))

        # 1) الوحدات
        modules_by_code = {}
        for m in MODULES:
            obj, created = AppModule.objects.update_or_create(
                code=m['code'],
                defaults={
                    'name': m['name'],
                    'icon': m['icon'],
                    'order': m['order'],
                    'is_active': True,
                },
            )
            modules_by_code[m['code']] = obj
            tag = 'NEW ' if created else 'OK  '
            self.stdout.write(f'  📦 [{tag}] {obj.name}')

        # 2) الصلاحيات
        created_count = 0
        for code, module in modules_by_code.items():
            ops = MODULE_OPERATIONS.get(code, DEFAULT_OPERATIONS)
            for op in ops:
                perm_code = f'{code}.{op}'
                perm_name = f'{OPERATION_NAMES[op]} {module.name}'
                obj, created = Permission.objects.update_or_create(
                    code=perm_code,
                    defaults={
                        'module': module,
                        'operation': op,
                        'name': perm_name,
                        'is_active': True,
                    },
                )
                if created:
                    created_count += 1
        self.stdout.write(self.style.SUCCESS(
            f'✅ تمت معالجة {Permission.objects.count()} صلاحية ({created_count} جديدة)'
        ))

        # 3) منح الأدمن كل الصلاحيات تلقائياً
        all_perms = Permission.objects.filter(is_active=True)
        admin_roles = Role.objects.filter(role_type=Role.RoleType.ADMIN)
        for role in admin_roles:
            role.permissions.set(all_perms)
            self.stdout.write(f'  👑 {role.name}: {all_perms.count()} صلاحية')

        self.stdout.write(self.style.SUCCESS('🎉 تم بنجاح'))
