# HistoricalRecords: run_kind on payroll_historicalpayrollrun

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0005_payroll_run_kind_and_allocations'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalpayrollrun',
            name='run_kind',
            field=models.CharField(
                choices=[('standard', 'مسير'), ('detailed', 'مسير تفصيلي')],
                db_index=True,
                default='standard',
                max_length=20,
                verbose_name='نوع المسير',
            ),
        ),
    ]
