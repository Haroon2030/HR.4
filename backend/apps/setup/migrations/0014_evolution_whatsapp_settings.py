from django.db import migrations, models


DEFAULT_EVENTS = ['QRCODE_UPDATED', 'CONNECTION_UPDATE', 'MESSAGES_UPSERT']


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0013_operationsreportsettings_whatsapp'),
    ]

    operations = [
        migrations.CreateModel(
            name='EvolutionWhatsAppSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('api_url', models.URLField(blank=True, default='', help_text='مثل http://72.61.107.230:8081', max_length=500, verbose_name='رابط Evolution API')),
                ('api_key', models.CharField(blank=True, default='', max_length=255, verbose_name='مفتاح API')),
                ('instance_name', models.CharField(blank=True, default='hr', help_text='اسم إنجليزي فقط — مثل hr أو main', max_length=64, verbose_name='اسم Instance')),
                ('is_enabled', models.BooleanField(default=False, verbose_name='تفعيل إرسال WhatsApp')),
                ('webhook_enabled', models.BooleanField(default=True, verbose_name='تفعيل Webhook')),
                ('webhook_events', models.JSONField(blank=True, default=list, help_text='أحداث Evolution API المراد استقبالها.', verbose_name='أحداث Webhook')),
                ('connection_status', models.CharField(choices=[('unknown', 'غير معروف'), ('open', 'متصل'), ('close', 'غير متصل'), ('connecting', 'جاري الربط')], default='unknown', max_length=20, verbose_name='حالة الاتصال')),
                ('last_qrcode_base64', models.TextField(blank=True, default='', verbose_name='آخر QR')),
                ('last_webhook_at', models.DateTimeField(blank=True, null=True, verbose_name='آخر Webhook')),
                ('last_status_sync_at', models.DateTimeField(blank=True, null=True, verbose_name='آخر مزامنة حالة')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')),
            ],
            options={
                'verbose_name': 'إعدادات WhatsApp (Evolution)',
                'verbose_name_plural': 'إعدادات WhatsApp (Evolution)',
                'db_table': 'setup_evolutionwhatsappsettings',
            },
        ),
        migrations.RunPython(
            code=lambda apps, schema_editor: apps.get_model('setup', 'EvolutionWhatsAppSettings').objects.get_or_create(
                pk=1,
                defaults={'webhook_events': DEFAULT_EVENTS},
            ),
            reverse_code=migrations.RunPython.noop,
        ),
    ]
