"""صلاحيات تعديل وحذف سجلات تبويبات الموظف (إفادات، سلف، مخصصات)."""

from django.db import migrations

PERMS = (
    ('employees.edit_statement', 'edit_statement', 'تعديل إفادة / إنذار'),
    ('employees.delete_statement', 'delete_statement', 'حذف إفادة / إنذار'),
    ('employees.edit_loan', 'edit_loan', 'تعديل سلفة موظف'),
    ('employees.delete_loan', 'delete_loan', 'حذف سلفة موظف'),
    ('employees.edit_ledger', 'edit_ledger', 'تعديل سجل مخصصات'),
    ('employees.delete_ledger', 'delete_ledger', 'حذف سجل مخصصات'),
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
        ('core', '0047_employee_absence_manage_permissions'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
