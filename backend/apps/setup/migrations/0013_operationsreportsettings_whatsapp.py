from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0012_alter_operationsreportsettings_send_time_help'),
    ]

    operations = [
        migrations.AddField(
            model_name='operationsreportsettings',
            name='recipient_phones',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='مفاتيح الأدوار: system_manager, hr_manager, ...',
                verbose_name='جوال واتساب حسب الدور',
            ),
        ),
        migrations.AddField(
            model_name='operationsreportsettings',
            name='send_via_whatsapp',
            field=models.BooleanField(
                default=False,
                help_text='يرسل ملف PDF عبر WhatsApp (Evolution API) للأرقام المربوطة.',
                verbose_name='إرسال عبر واتساب',
            ),
        ),
    ]
