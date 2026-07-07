"""إنشاء صلاحيات الشاشات الفرعية للحضور ومنحها للأدوار التي لديها attendance.view."""

from django.db import migrations

ATTENDANCE_VIEW = 'attendance.view'

SCREEN_MODULES = (
    ('attendance_screen_devices', 'الحضور — أجهزة البصمة', 111),
    ('attendance_screen_report', 'الحضور — تقرير البصمة', 112),
    ('attendance_screen_late_alerts', 'الحضور — إنذار تأخير البصمة', 113),
    ('attendance_screen_records', 'الحضور — سجلات الحضور', 114),
)

SCREEN_PERMISSIONS = tuple(
    (f'{code}.view', name, code)
    for code, name, _order in SCREEN_MODULES
)


def create_attendance_screen_permissions(apps, schema_editor):
    AppModule = apps.get_model('core', 'AppModule')
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')
    RolePermission = Role.permissions.through

    perm_ids: list[int] = []
    for module_code, module_name, order in SCREEN_MODULES:
        module, _ = AppModule.objects.update_or_create(
            code=module_code,
            defaults={
                'name': module_name,
                'icon': 'fingerprint',
                'order': order,
                'is_active': True,
            },
        )
        perm_code, perm_name, _ = next(
            item for item in SCREEN_PERMISSIONS if item[2] == module_code
        )
        perm, _ = Permission.objects.update_or_create(
            code=perm_code,
            defaults={
                'name': perm_name,
                'module': module,
                'operation': 'view',
                'is_active': True,
            },
        )
        perm_ids.append(perm.pk)

    base_perm = Permission.objects.filter(code=ATTENDANCE_VIEW).first()
    if not base_perm:
        return

    role_ids = (
        Role.objects.filter(permissions=base_perm, is_active=True)
        .values_list('pk', flat=True)
        .distinct()
    )
    for role_id in role_ids:
        for perm_id in perm_ids:
            RolePermission.objects.get_or_create(role_id=role_id, permission_id=perm_id)


def reverse_create(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')
    RolePermission = apps.get_model('core', 'Role').permissions.through

    codes = [item[0] for item in SCREEN_PERMISSIONS]
    perm_ids = list(Permission.objects.filter(code__in=codes).values_list('pk', flat=True))
    if perm_ids:
        RolePermission.objects.filter(permission_id__in=perm_ids).delete()
    Permission.objects.filter(code__in=codes).delete()
    AppModule.objects.filter(code__in=[item[0] for item in SCREEN_MODULES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0051_hr_officer_attendance_view'),
    ]

    operations = [
        migrations.RunPython(create_attendance_screen_permissions, reverse_create),
    ]
