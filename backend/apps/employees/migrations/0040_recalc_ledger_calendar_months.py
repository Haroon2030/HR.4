"""إعادة حساب المخصصات بعد تصحيح عدّ الأشهر التقويمية (مباشرة يوم 1)."""
from django.db import migrations


def _recalc_ledgers(apps, schema_editor):
    EmployeeLedger = apps.get_model('employees', 'EmployeeLedger')
    if not EmployeeLedger.objects.exists():
        return
    from apps.employees.services.ledger_recalculate import recalculate_all_employee_ledgers

    recalculate_all_employee_ledgers(dry_run=False)


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0039_recalc_accrual_ledger_30_day_rule'),
        ('payroll', '0009_cash_shortage_feature'),
    ]

    operations = [
        migrations.RunPython(_recalc_ledgers, migrations.RunPython.noop),
    ]
