from django.db import migrations, models


class Migration(migrations.Migration):
    """مسير قياسي لكل (فرع، شهر، نوع راتب، شركة كفالة) بدل (فرع، شهر، نوع راتب) فقط."""

    dependencies = [
        ('payroll', '0009_cash_shortage_feature'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='payrollrun',
            name='payroll_uniq_standard_run',
        ),
        migrations.AddConstraint(
            model_name='payrollrun',
            constraint=models.UniqueConstraint(
                condition=models.Q(('run_kind', 'standard')),
                fields=('branch', 'period_year', 'period_month', 'salary_mode', 'sponsorship'),
                name='payroll_uniq_standard_run',
            ),
        ),
    ]
