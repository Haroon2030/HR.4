"""صلاحية «ربط موظف بجهاز البصمة» (attendance.link_employee) لأخصائي ومدير الموارد.

كان الربط مشروطاً بـ attendance.manage (إدارة الأجهزة كلها). الصلاحية الجديدة مستقلة:
تُمنح لدورَي الموارد البشرية (مع شاشة الأجهزة اللازمة لفتح نافذة الربط)، ولكل دور يملك
attendance.manage حالياً كي لا يفقد أحد ما كان يملكه. وللمدير تعديلها من مصفوفة الصلاحيات.
"""
from django.db import migrations

CODE = 'attendance.link_employee'
HR_ROLE_TYPES = ('hr_officer', 'hr_manager')
DEVICES_SCREEN = 'attendance_screen_devices.view'


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')

    module = AppModule.objects.filter(code='attendance').first()
    if module is None:
        return
    perm = Permission.objects.filter(code=CODE).first()
    if perm is None:
        perm = Permission.objects.create(
            module=module, operation='link_employee',
            code=CODE, name='ربط موظف بجهاز البصمة', is_active=True,
        )
    hr_roles = Role.objects.filter(role_type__in=HR_ROLE_TYPES)
    manage_roles = Role.objects.filter(permissions__code='attendance.manage')
    for role in list(hr_roles) + list(manage_roles):
        role.permissions.add(perm)
    screen = Permission.objects.filter(code=DEVICES_SCREEN).first()
    if screen is not None:
        for role in hr_roles:
            role.permissions.add(screen)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0061_hr_officer_salary_permissions'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
