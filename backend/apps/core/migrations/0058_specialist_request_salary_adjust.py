"""منح دور «موظف الرفع» (specialist) صلاحية تقديم طلب تعديل راتب.

الصلاحية `employees.request_salary_adjust` أضيق من `employees.edit_salary`:
تُظهر «تعديل راتب» في الإضافة السريعة وتُرسل طلباً يمر بدورة الموافقات،
دون عرض الرواتب أو تعديلها مباشرة. تُنشأ هنا إن لم تكن موجودة (المزامنة
بعد migrate تنشئها أيضاً بنفس الرمز) وتُضاف للدور مرة واحدة فقط؛ وللمدير
سحبها لاحقاً من مصفوفة الصلاحيات.
"""
from django.db import migrations

CODE = 'employees.request_salary_adjust'


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    AppModule = apps.get_model('core', 'AppModule')

    module = AppModule.objects.filter(code='employees').first()
    if module is None:
        return
    perm = Permission.objects.filter(code=CODE).first()
    if perm is None:
        perm = Permission.objects.create(
            module=module,
            operation='request_salary_adjust',
            code=CODE,
            name='تقديم طلب تعديل راتب الموظفين',
            is_active=True,
        )
    for role in Role.objects.filter(role_type='specialist'):
        role.permissions.add(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0057_pendingaction_accountant_stage'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
