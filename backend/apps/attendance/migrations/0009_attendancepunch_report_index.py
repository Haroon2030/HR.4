from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0008_biometricdevice_agent_api_key'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='attendancepunch',
            index=models.Index(
                fields=['is_deleted', 'punched_at'],
                name='att_punch_del_punched_idx',
            ),
        ),
    ]
