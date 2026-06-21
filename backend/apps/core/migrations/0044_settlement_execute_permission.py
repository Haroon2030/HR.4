"""صلاحية تنفيذ تصفية نهاية خدمة / استقالة — افتراضياً أدمن + مدير الموارد البشرية."""

from django.db import migrations

PERM_CODE = 'employee_tab_termination.execute'
MODULE_CODE = 'employee_tab_termination'


def forward(apps, schema_editor):
    AppModule = apps.get_model('core', 'AppModule')
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')

    module, _ = AppModule.objects.update_or_create(
        code=MODULE_CODE,
        defaults={
            'name': 'تبويب — التصفيات',
            'icon': 'layout-grid',
            'order': 146,
            'is_active': True,
        },
    )
    perm, _ = Permission.objects.update_or_create(
        code=PERM_CODE,
        defaults={
            'module': module,
            'operation': 'execute',
            'name': 'تنفيذ — تصفية نهاية خدمة / استقالة',
            'is_active': True,
        },
    )

    for role_type in ('admin', 'hr_manager'):
        for role in Role.objects.filter(role_type=role_type, is_active=True):
            role.permissions.add(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0043_remove_contract_end_action_type'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
