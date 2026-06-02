from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0004_administration_historicaladministration'),
    ]

    operations = [
        migrations.AddField(
            model_name='administration',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف'),
        ),
        migrations.AlterField(
            model_name='administration',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False, verbose_name='محذوف'),
        ),
        migrations.AddField(
            model_name='historicaladministration',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف'),
        ),
        migrations.AlterField(
            model_name='historicaladministration',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False, verbose_name='محذوف'),
        ),
    ]
