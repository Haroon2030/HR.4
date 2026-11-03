"""نقل صلاحية «ربط موظف بجهاز البصمة» إلى صف شاشة «الحضور — أجهزة البصمة» في المصفوفة.

الكود القديم attendance.link_employee يصبح attendance_screen_devices.link_employee
مع الإبقاء على الأدوار الممنوحة له.
"""
from django.db import migrations

OLD = 'attendance.link_employee'
NEW = 'attendance_screen_devices.link_employee'


def forward(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')
    module = AppModule.objects.filter(code='attendance_screen_devices').first()
    if module is None:
        return
    old = Permission.objects.filter(code=OLD).first()
    new = Permission.objects.filter(code=NEW).first()
    if old is None:
        return
    if new is None:
        old.module = module
        old.code = NEW
        old.save(update_fields=['module', 'code'])
        return
    for role in list(old.roles.all()) if hasattr(old, 'roles') else []:
        role.permissions.add(new)
    old.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0063_employees_quick_add_permission'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
