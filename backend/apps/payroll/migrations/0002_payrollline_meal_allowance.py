"""إضافة بدل التغذية لسطر مسير الرواتب."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='payrollline',
            name='meal_allowance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='بدل التغذية'),
        ),
        migrations.AddField(
            model_name='historicalpayrollline',
            name='meal_allowance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='بدل التغذية'),
        ),
    ]
