"""فصل أزرار تصدير/استيراد الموظفين وزر «تعديل / إكمال البيانات» بصلاحيات مستقلة.

كانت مرتبطة بـ employees.view / employees.add / employees.edit، ودور «موظف الرفع»
(specialist) يحتاج تلك الصلاحيات لعمله فلا يمكن سحبها. الصلاحيات الجديدة تُمنح
لكل دور يملك الصلاحية المقابلة حالياً — فلا يتغيّر شيء لغيره — عدا موظف الرفع.
ويمكن للمدير تعديلها لاحقاً من مصفوفة الصلاحيات.
"""
from django.db import migrations

UPLOAD_ROLE_TYPE = 'specialist'

# (الرمز الجديد، العملية، الاسم، الصلاحية الحالية التي كانت تُظهر الزر)
NEW_PERMS = [
    ('employees.export', 'export', 'تصدير الموظفين', 'employees.view'),
    ('employees.import', 'import', 'استيراد الموظفين', 'employees.add'),
    ('employees.edit_profile', 'edit_profile', 'زر تعديل / إكمال بيانات الموظف', 'employees.edit'),
]


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')

    module = AppModule.objects.filter(code='employees').first()
    if module is None:
        return
    for code, operation, name, source_code in NEW_PERMS:
        perm = Permission.objects.filter(code=code).first()
        if perm is None:
            perm = Permission.objects.create(
                module=module, operation=operation, code=code, name=name, is_active=True,
            )
        roles = (
            Role.objects.filter(permissions__code=source_code)
            .exclude(role_type=UPLOAD_ROLE_TYPE)
            .distinct()
        )
        for role in roles:
            role.permissions.add(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0058_specialist_request_salary_adjust'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
