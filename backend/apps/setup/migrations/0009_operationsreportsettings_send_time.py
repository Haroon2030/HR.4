"""وقت الإرسال بدل send_hour."""
from datetime import time

from django.db import migrations, models


def copy_send_hour_to_send_time(apps, schema_editor):
    OperationsReportSettings = apps.get_model('setup', 'OperationsReportSettings')
    for row in OperationsReportSettings.objects.all():
        hour = getattr(row, 'send_hour', 12) or 12
        row.send_time = time(int(hour), 0, 0)
        row.save(update_fields=['send_time'])


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0008_operationsreportsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='operationsreportsettings',
            name='send_time',
            field=models.TimeField(
                default=time(12, 0, 0),
                help_text='يُرسل التقرير يومياً عند هذا الوقت (توقيت السيرفر).',
                verbose_name='وقت الإرسال',
            ),
        ),
        migrations.RunPython(copy_send_hour_to_send_time, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='operationsreportsettings',
            name='send_hour',
        ),
    ]
