"""بريد المستلمين حسب الدور."""
from django.db import migrations, models


def migrate_recipient_email_to_json(apps, schema_editor):
    OperationsReportSettings = apps.get_model('setup', 'OperationsReportSettings')
    for row in OperationsReportSettings.objects.all():
        legacy = (getattr(row, 'recipient_email', '') or '').strip()
        emails = dict(row.recipient_emails or {})
        if legacy and not emails.get('system_manager'):
            emails['system_manager'] = legacy
        row.recipient_emails = emails
        row.save(update_fields=['recipient_emails'])


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0009_operationsreportsettings_send_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='operationsreportsettings',
            name='recipient_emails',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='مفاتيح الأدوار: system_manager, hr_manager, ...',
                verbose_name='بريد المستلمين حسب الدور',
            ),
        ),
        migrations.RunPython(migrate_recipient_email_to_json, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='operationsreportsettings',
            name='recipient_email',
            field=models.EmailField(
                blank=True,
                default='',
                help_text='للتوافق — يُزامَن من مدير النظام عند الحفظ.',
                max_length=254,
                verbose_name='البريد المستلم (قديم)',
            ),
        ),
    ]
