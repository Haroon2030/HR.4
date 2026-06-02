from django.db import migrations, models

ROLE_TYPE_CHOICES = [
    ('admin', 'مدير النظام'),
    ('hr_manager', 'مدير موارد بشرية'),
    ('hr_officer', 'موظف موارد'),
    ('admin_manager', 'مدير إدارة'),
    ('manager', 'مدير فرع'),
    ('specialist', 'أخصائي'),
    ('employee', 'موظف'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_rename_approve_administration_permission'),
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
