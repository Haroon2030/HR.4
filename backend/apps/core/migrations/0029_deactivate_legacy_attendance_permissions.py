# Data migration: attendance module was never implemented; permissions linger in DB.

from django.db import migrations


def deactivate_attendance_permissions(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')
    Role = apps.get_model('core', 'Role')

    qs = Permission.objects.filter(code__startswith='attendance.')
    perm_ids = list(qs.values_list('id', flat=True))
    if not perm_ids:
        return

    RolePermission = Role.permissions.through
    RolePermission.objects.filter(permission_id__in=perm_ids).delete()

    qs.update(is_active=False)
    AppModule.objects.filter(code='attendance').update(is_active=False)


def reverse_deactivate(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')
    Permission.objects.filter(code__startswith='attendance.').update(is_active=True)
    AppModule.objects.filter(code='attendance').update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0028_backup_trigger_migrate'),
    ]

    operations = [
        migrations.RunPython(deactivate_attendance_permissions, reverse_deactivate),
    ]
