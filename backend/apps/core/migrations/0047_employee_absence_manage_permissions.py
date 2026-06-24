"""صلاحيات تعديل وحذف غيابات الموظف — افتراضياً أدمن + مدير الموارد البشرية."""

from django.db import migrations

PERMS = (
    ('employees.edit_absence', 'edit_absence', 'تعديل غياب موظف'),
    ('employees.delete_absence', 'delete_absence', 'حذف غياب موظف'),
)


def forward(apps, schema_editor):
    AppModule = apps.get_model('core', 'AppModule')
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')

    module, _ = AppModule.objects.update_or_create(
        code='employees',
        defaults={
            'name': 'الموظفين',
            'icon': 'users',
            'order': 10,
            'is_active': True,
        },
    )

    perm_ids = []
    for code, operation, name in PERMS:
        perm, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'operation': operation,
                'name': name,
                'is_active': True,
            },
        )
        perm_ids.append(perm.id)

    for role_type in ('admin', 'hr_manager'):
        for role in Role.objects.filter(role_type=role_type, is_active=True):
            role.permissions.add(*perm_ids)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0046_tighten_upload_extensions'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
