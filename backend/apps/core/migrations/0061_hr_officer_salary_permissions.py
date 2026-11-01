"""منح دور «أخصائي الموارد» (hr_officer) عرض الراتب وتعديل بياناته.

تُنشأ الصلاحيتان إن لم تكونا موجودتين وتُضافان للدور مرة واحدة؛ وللمدير سحبهما
لاحقاً من مصفوفة الصلاحيات.
"""
from django.db import migrations

ROLE_TYPE = 'hr_officer'
PERMS = [
    ('employees.view_salary', 'view_salary', 'عرض رواتب الموظفين'),
    ('employees.edit_salary', 'edit_salary', 'تعديل رواتب الموظفين'),
]


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')

    module = AppModule.objects.filter(code='employees').first()
    if module is None:
        return
    for code, operation, name in PERMS:
        perm = Permission.objects.filter(code=code).first()
        if perm is None:
            perm = Permission.objects.create(
                module=module, operation=operation, code=code, name=name, is_active=True,
            )
        for role in Role.objects.filter(role_type=ROLE_TYPE):
            role.permissions.add(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0060_pendingaction_signed_settlement'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
