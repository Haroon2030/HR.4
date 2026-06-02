"""تحديث تسميات role_type للعرض (القيم البرمجية دون تغيير)."""

from django.db import migrations, models

ROLE_TYPE_CHOICES = [
    ('admin', 'مدير النظام (صلاحيات كاملة)'),
    ('hr_manager', 'مدير الموارد البشرية'),
    ('hr_officer', 'موظف تنفيذ الموارد البشرية'),
    ('admin_manager', 'مدير الإدارة (موافقة أولى)'),
    ('manager', 'مدير الفرع (موافقة أولى)'),
    ('specialist', 'أخصائي الموارد البشرية'),
    ('employee', 'موظف عادي'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0035_add_admin_manager_role_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicalrole',
            name='role_type',
            field=models.CharField(
                choices=ROLE_TYPE_CHOICES,
                default='employee',
                max_length=20,
                verbose_name='نوع الدور',
            ),
        ),
        migrations.AlterField(
            model_name='role',
            name='role_type',
            field=models.CharField(
                choices=ROLE_TYPE_CHOICES,
                default='employee',
                max_length=20,
                verbose_name='نوع الدور',
            ),
        ),
    ]
