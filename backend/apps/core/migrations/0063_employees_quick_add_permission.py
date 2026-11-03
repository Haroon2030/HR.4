"""صلاحية مستقلة لزر «الإضافة السريعة» في ملف الموظف (employees.quick_add).

كان الزر مرتبطاً بـ employees.edit. تُمنح الصلاحية الجديدة لكل دور يملك employees.edit
حالياً فلا يتغيّر شيء لأحد، ويمكن للمدير بعدها سحبها أو منحها من مصفوفة الصلاحيات.
"""
from django.db import migrations

CODE = 'employees.quick_add'


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')

    module = AppModule.objects.filter(code='employees').first()
    if module is None:
        return
    perm = Permission.objects.filter(code=CODE).first()
    if perm is None:
        perm = Permission.objects.create(
            module=module, operation='quick_add',
            code=CODE, name='زر الإضافة السريعة في ملف الموظف', is_active=True,
        )
    for role in Role.objects.filter(permissions__code='employees.edit').distinct():
        role.permissions.add(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0062_attendance_link_employee_permission'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
