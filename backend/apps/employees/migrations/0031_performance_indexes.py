from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0030_employee_contract_fields'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['branch', 'status'], name='emp_branch_status_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['branch', 'is_deleted'], name='emp_branch_del_idx'),
        ),
        migrations.AddIndex(
            model_name='employmentrequest',
            index=models.Index(fields=['status', 'branch'], name='er_status_branch_idx'),
        ),
        migrations.AddIndex(
            model_name='employeeabsence',
            index=models.Index(fields=['employee', 'absence_date'], name='empabs_emp_date_idx'),
        ),
    ]
