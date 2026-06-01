from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0007_alter_employeebiometricsettings_is_deleted'),
    ]

    operations = [
        migrations.AddField(
            model_name='biometricdevice',
            name='agent_api_key',
            field=models.CharField(
                blank=True,
                default='',
                help_text='SHA-256 لمفتاح الوكيل المحلي — يُولَّد من لوحة الإدارة أو الأمر generate_attendance_agent_key',
                max_length=64,
                verbose_name='مفتاح وكيل البصمة (مُجزّأ)',
            ),
        ),
    ]
