from django.db import migrations, models


ACTION_TYPE_CHOICES = [
    ('leave', 'تقديم إجازة'),
    ('transfer', 'نقل'),
    ('salary_adjust', 'تعديل راتب'),
    ('terminate', 'إنهاء خدمة'),
    ('reactivate', 'إعادة تنشيط'),
    ('custody_receive', 'استلام عهدة'),
    ('custody_clear', 'تصفية عهدة'),
    ('business_trip', 'رحلة عمل'),
    ('loan_request', 'تقديم سلفة'),
    ('absence', 'تسجيل غياب'),
    ('contract_end', 'انتهاء عقد'),
    ('end_of_service', 'تصفية نهاية خدمة / استقالة'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_rename_core_pendin_adminis_d3e0f8_idx_core_pendin_adminis_27f153_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicalpendingaction',
            name='action_type',
            field=models.CharField(
                choices=ACTION_TYPE_CHOICES,
                db_index=True,
                max_length=20,
                verbose_name='نوع العملية',
            ),
        ),
        migrations.AlterField(
            model_name='pendingaction',
            name='action_type',
            field=models.CharField(
                choices=ACTION_TYPE_CHOICES,
                db_index=True,
                max_length=20,
                verbose_name='نوع العملية',
            ),
        ),
    ]
