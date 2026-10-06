"""ضمان صلاحيات أخصائي إدخال البيانات (specialist) على الموظفين.

العمليات السريعة في ملف الموظف (سلفة، إجازة، غياب، عهدة، نقل، جدول دوام، إفادات)
تتطلب `employees.edit`. بعض بيئات الإنتاج فقد الدور هذه الصلاحية من مصفوفة الأدوار،
فيظهر للأخصائي «ليس لديك صلاحية للوصول إلى هذه الصفحة» عند تقديم سلفة.

هذه الترقية تضيف الصلاحيات الأساسية للدور إن كانت ناقصة (لا تحذف شيئاً).
التصفية وتعديل الراتب لها صلاحيات مستقلة ولا تتأثر.

ذرّية وآمنة عند التكرار.
"""
from django.db import migrations

SPECIALIST_PERMISSIONS = ('employees.view', 'employees.add', 'employees.edit')


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')

    role = Role.objects.filter(role_type='specialist').first()
    if role is None:
        return
    existing = set(role.permissions.values_list('code', flat=True))
    missing = [c for c in SPECIALIST_PERMISSIONS if c not in existing]
    if not missing:
        return
    perms = list(Permission.objects.filter(code__in=missing))
    if perms:
        role.permissions.add(*perms)
        print(f"  → أُضيفت صلاحيات {[p.code for p in perms]} لدور أخصائي إدخال البيانات")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0054_userprofile_assigned_administrations'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
