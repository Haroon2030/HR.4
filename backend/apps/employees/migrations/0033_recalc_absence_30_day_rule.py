"""إعادة حساب سجلات الغياب على قاعدة 30 يوماً."""
from decimal import Decimal

from django.db import migrations, models

STANDARD_MONTH_DAYS = 30
_GROSS_FIELDS = (
    'basic_salary',
    'housing_allowance',
    'transport_allowance',
    'other_allowance',
    'cash_amount',
    'meal_allowance',
)


def _gross_from_employee_row(row) -> Decimal:
    """إجمالي الراتب من حقول DB (total_salary خاصية وليست عموداً)."""
    if not row:
        return Decimal('0')
    return sum((Decimal(row.get(f) or 0) for f in _GROSS_FIELDS), Decimal('0'))


def _recalc_absences(apps, schema_editor):
    EmployeeAbsence = apps.get_model('employees', 'EmployeeAbsence')
    Employee = apps.get_model('employees', 'Employee')

    for absence in EmployeeAbsence.objects.all().iterator():
        salary = absence.total_salary_snapshot
        if not salary:
            row = (
                Employee.objects.filter(pk=absence.employee_id)
                .values(*_GROSS_FIELDS)
                .first()
            )
            salary = _gross_from_employee_row(row)
        salary = Decimal(salary or 0)
        daily = (salary / Decimal(STANDARD_MONTH_DAYS)).quantize(Decimal('0.01'))
        deduction = (daily * Decimal(absence.days or 0)).quantize(Decimal('0.01'))
        EmployeeAbsence.objects.filter(pk=absence.pk).update(
            month_days=STANDARD_MONTH_DAYS,
            total_salary_snapshot=salary,
            daily_rate=daily,
            deduction_amount=deduction,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0032_remove_employee_emp_branch_status_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employeeabsence',
            name='daily_rate',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='إجمالي الراتب ÷ 30',
                max_digits=12,
                verbose_name='سعر اليوم (محسوب)',
            ),
        ),
        migrations.RunPython(_recalc_absences, migrations.RunPython.noop),
    ]
