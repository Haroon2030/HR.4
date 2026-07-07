"""منح أخصائي الموارد صلاحية عرض البصمة واستعادة وحدة attendance."""

from django.db import migrations


ATTENDANCE_VIEW = 'attendance.view'


def grant_hr_officer_attendance_view(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')
    Role = apps.get_model('core', 'Role')

    AppModule.objects.filter(code='attendance').update(is_active=True)
    Permission.objects.filter(code__startswith='attendance.').update(is_active=True)

    perm = Permission.objects.filter(code=ATTENDANCE_VIEW).first()
    if not perm:
        return

    role = Role.objects.filter(role_type='hr_officer', is_active=True).first()
    if not role:
        return

    RolePermission = Role.permissions.through
    RolePermission.objects.get_or_create(role_id=role.pk, permission_id=perm.pk)


def reverse_grant(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')

    perm = Permission.objects.filter(code=ATTENDANCE_VIEW).first()
    role = Role.objects.filter(role_type='hr_officer').first()
    if not perm or not role:
        return
    RolePermission = Role.permissions.through
    RolePermission.objects.filter(role_id=role.pk, permission_id=perm.pk).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0050_alter_historicalrole_role_type_alter_role_role_type'),
    ]

    operations = [
        migrations.RunPython(grant_hr_officer_attendance_view, reverse_grant),
    ]
