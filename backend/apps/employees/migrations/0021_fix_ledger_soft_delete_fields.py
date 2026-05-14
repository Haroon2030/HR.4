# Fix: add missing is_deleted and deleted_at columns to existing table

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0020_employeeledger_historicalemployeeledger'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeledger',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False, verbose_name='محذوف'),
        ),
        migrations.AddField(
            model_name='employeeledger',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف'),
        ),
        migrations.AddField(
            model_name='historicalemployeeledger',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False, verbose_name='محذوف'),
        ),
        migrations.AddField(
            model_name='historicalemployeeledger',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف'),
        ),
    ]
