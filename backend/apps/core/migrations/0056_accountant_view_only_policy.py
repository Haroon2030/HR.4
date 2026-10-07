"""سياسة دور المحاسب: اطّلاع شامل بلا إضافة/تعديل/حذف + أدوات التعميد.

تُضبط صلاحيات الدور مرة واحدة هنا (تحذف أي صلاحية كتابة كانت ممنوحة له)،
وبعدها تُضاف صلاحيات العرض المستجدة تلقائياً بعد كل مزامنة للصلاحيات.
آمنة عند التكرار، ولا تفعل شيئاً إن لم يوجد دور المحاسب.
"""
from django.db import migrations

from apps.core.role_policies import sync_accountant_role


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    role = sync_accountant_role(Role, Permission)
    if role is not None:
        print(f"  → طُبّقت سياسة المحاسب على الدور id={role.id} ({role.permissions.count()} صلاحية عرض/تعميد)")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0055_ensure_specialist_employee_permissions'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
