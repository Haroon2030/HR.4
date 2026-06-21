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
    ('cash_shortage', 'عجز كاشير'),
    ('end_of_service', 'تصفية نهاية خدمة / استقالة'),
]


def migrate_contract_end_to_end_of_service(apps, schema_editor):
    PendingAction = apps.get_model('core', 'PendingAction')
    HistoricalPendingAction = apps.get_model('core', 'HistoricalPendingAction')
    PendingAction.objects.filter(action_type='contract_end').update(action_type='end_of_service')
    HistoricalPendingAction.objects.filter(action_type='contract_end').update(action_type='end_of_service')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0042_whatsapp_message_log'),
    ]

    operations = [
        migrations.RunPython(
            migrate_contract_end_to_end_of_service,
            migrations.RunPython.noop,
        ),
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
