"""إضافة الشركة ونوع الراتب للمسير مع فصل مسير نقدي/تحويل لكل فرع وشهر."""

from django.db import migrations, models
import django.db.models.deletion


def backfill_company_and_salary_mode(apps, schema_editor):
    PayrollRun = apps.get_model('payroll', 'PayrollRun')
    for run in PayrollRun.objects.select_related('branch').iterator():
        changed = False
        if not run.salary_mode:
            run.salary_mode = 'transfer'
            changed = True
        if not run.company_id and run.branch_id:
            run.company_id = run.branch.company_id
            changed = True
        if changed:
            run.save(update_fields=['salary_mode', 'company_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0002_payrollline_meal_allowance'),
    ]

    operations = [
        migrations.AddField(
            model_name='payrollrun',
            name='company',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='payroll_runs',
                to='core.company',
                verbose_name='الشركة',
            ),
        ),
        migrations.AddField(
            model_name='payrollrun',
            name='salary_mode',
            field=models.CharField(
                choices=[('cash', 'نقدي'), ('transfer', 'تحويل')],
                db_index=True,
                default='transfer',
                max_length=20,
                verbose_name='نوع الراتب',
            ),
        ),
        migrations.AddField(
            model_name='historicalpayrollrun',
            name='company',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+',
                to='core.company',
                verbose_name='الشركة',
            ),
        ),
        migrations.AddField(
            model_name='historicalpayrollrun',
            name='salary_mode',
            field=models.CharField(
                choices=[('cash', 'نقدي'), ('transfer', 'تحويل')],
                db_index=True,
                default='transfer',
                max_length=20,
                verbose_name='نوع الراتب',
            ),
        ),
        migrations.RunPython(backfill_company_and_salary_mode, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='payrollrun',
            unique_together={('branch', 'period_year', 'period_month', 'salary_mode')},
        ),
    ]
