# approve_administration (22 chars) exceeded max_length=20; widen field + use approve_admin.

from django.db import migrations, models

_PERMISSION_OPERATION_CHOICES = [
    ('view', 'عرض'),
    ('add', 'إضافة'),
    ('edit', 'تعديل'),
    ('delete', 'حذف'),
    ('approve_branch', 'موافقة الفرع'),
    ('approve_admin', 'موافقة الإدارة'),
    ('approve_gm', 'موافقة المدير العام'),
    ('approve_officer', 'تنفيذ موظف الموارد'),
    ('return', 'إرجاع'),
    ('resubmit', 'إعادة إرسال'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_backfill_administration_on_requests'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicalpermission',
            name='operation',
            field=models.CharField(
                choices=_PERMISSION_OPERATION_CHOICES,
                max_length=32,
                verbose_name='العملية',
            ),
        ),
        migrations.AlterField(
            model_name='permission',
            name='operation',
            field=models.CharField(
                choices=_PERMISSION_OPERATION_CHOICES,
                max_length=32,
                verbose_name='العملية',
            ),
        ),
    ]
