"""
عرض نظرة عامة على نظام الصلاحيات
"""
from apps.core.models import AppModule, Permission, Role

print('\n' + '='*60)
print('🎯 نظرة عامة على نظام الصلاحيات')
print('='*60 + '\n')

# الوحدات
modules = AppModule.objects.all().order_by('order')
print(f'📦 عدد الوحدات: {modules.count()}')
print(f'🔐 عدد الصلاحيات: {Permission.objects.count()}')
print(f'👥 عدد الأدوار: {Role.objects.count()}\n')

print('-'*60)
print('الوحدات والصلاحيات:')
print('-'*60)

for m in modules:
    print(f'\n{m.order}. {m.name} ({m.code}) - أيقونة: {m.icon}')
    perms = m.permissions.all()
    for p in perms[:5]:
        print(f'   ✓ {p.name} ({p.code})')
    if perms.count() > 5:
        print(f'   ... وصلاحيات أخرى ({perms.count() - 5})')
    print(f'   إجمالي: {perms.count()} صلاحية')

print('\n' + '-'*60)
print('الأدوار:')
print('-'*60)

for role in Role.objects.all():
    print(f'\n{role.name} ({role.get_role_type_display()})')
    print(f'   الصلاحيات: {role.permissions.count()}')
    print(f'   المستخدمون: {role.users.count()}')

print('\n' + '='*60)
