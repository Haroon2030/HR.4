# Generated manually — ربط المسير بشركة الكفالة من التهيئة

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0003_bank_historicalbank'),
        ('payroll', '0003_payrollrun_company_salary_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='payrollrun',
            name='sponsorship',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='payroll_runs',
                to='setup.sponsorship',
                verbose_name='شركة الكفالة',
            ),
        ),
        migrations.AddField(
            model_name='historicalpayrollrun',
            name='sponsorship',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+',
                to='setup.sponsorship',
                verbose_name='شركة الكفالة',
            ),
        ),
    ]
