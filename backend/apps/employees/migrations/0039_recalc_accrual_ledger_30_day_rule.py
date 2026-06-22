"""إعادة حساب سجل المخصصات على قاعدة الشهر = 30 يوماً."""
from django.db import migrations


def _recalc_accrual_ledgers(apps, schema_editor):
    EmployeeLedger = apps.get_model('employees', 'EmployeeLedger')
    if not EmployeeLedger.objects.exists():
        return
    from apps.employees.services.ledger_recalculate import recalculate_all_employee_ledgers

    recalculate_all_employee_ledgers(dry_run=False)


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0038_cash_shortage_document'),
        ('payroll', '0009_cash_shortage_feature'),
    ]

    operations = [
        migrations.RunPython(_recalc_accrual_ledgers, migrations.RunPython.noop),
    ]
