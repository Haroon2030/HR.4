"""شاشة «الحضور — ربط البصمة» مستقلة عن شاشة أجهزة البصمة.

تحل attendance_screen_link.view محل صلاحية الربط السابقة (attendance.link_employee /
attendance_screen_devices.link_employee) مع الإبقاء على الأدوار الممنوحة لها.
يُستثنى منها شاشة الأجهزة: من يُمنح الربط وحده لا يرى إدارة الأجهزة.
"""
from django.db import migrations

NEW = 'attendance_screen_link.view'
OLD_CODES = ('attendance_screen_devices.link_employee', 'attendance.link_employee')


def forward(apps, schema_editor):
    AppModule = apps.get_model('core', 'AppModule')
    Permission = apps.get_model('core', 'Permission')
    module, _ = AppModule.objects.update_or_create(
        code='attendance_screen_link',
        defaults={'name': 'الحضور — ربط البصمة', 'icon': 'fingerprint', 'order': 115, 'is_active': True},
    )
    new, _ = Permission.objects.update_or_create(
        code=NEW,
        defaults={'module': module, 'operation': 'view', 'name': 'الحضور — ربط البصمة', 'is_active': True},
    )
    for old in Permission.objects.filter(code__in=OLD_CODES):
        for role in list(old.roles.all()):
            role.permissions.add(new)
        for profile in list(old.extra_users.all()):
            profile.extra_permissions.add(new)
        for profile in list(old.denied_users.all()):
            profile.denied_permissions.add(new)
        old.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0064_link_employee_to_devices_screen'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
