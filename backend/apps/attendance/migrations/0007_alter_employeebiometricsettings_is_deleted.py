# Generated manually for makemigrations --check compliance

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0006_employeebiometricsettings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employeebiometricsettings',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False, verbose_name='محذوف'),
        ),
    ]
