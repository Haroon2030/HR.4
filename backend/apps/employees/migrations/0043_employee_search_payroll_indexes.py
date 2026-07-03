# Generated manually — فهارس أداء بحث الموظفين والمسير

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0042_employee_migration_opening_balances'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['employee_number'], name='emp_number_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['id_number'], name='emp_id_number_idx'),
        ),
        migrations.AddIndex(
            model_name='employeeleave',
            index=models.Index(
                fields=['employee', 'date_from', 'date_to'],
                name='empleave_emp_dates_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='employeeleave',
            index=models.Index(fields=['applied_to_payroll'], name='empleave_payroll_idx'),
        ),
        migrations.AddIndex(
            model_name='employeestatement',
            index=models.Index(
                fields=['employee', 'statement_date'],
                name='empstmt_emp_date_idx',
            ),
        ),
    ]
