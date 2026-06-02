"""Rename operations.approve_administration → operations.approve_admin if present."""

from django.db import migrations


def rename_permission(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    Permission.objects.filter(code='operations.approve_administration').update(
        code='operations.approve_admin',
        operation='approve_admin',
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_alter_permission_operation_max_length'),
    ]

    operations = [
        migrations.RunPython(rename_permission, noop_reverse),
    ]
