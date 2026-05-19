"""Backfill NULL salary/allowance decimals before NOT NULL enforcement at save time."""

from decimal import Decimal

from django.db import migrations


def backfill_null_decimals(apps, schema_editor):
    Employee = apps.get_model('employees', 'Employee')
    EmploymentRequest = apps.get_model('employees', 'EmploymentRequest')
    zero = Decimal('0')
    for model in (Employee, EmploymentRequest):
        for field_name in (
            'basic_salary',
            'housing_allowance',
            'transport_allowance',
            'other_allowance',
            'cash_amount',
            'insurance_deduction_rate',
        ):
            if not hasattr(model, field_name):
                continue
            model.objects.filter(**{f'{field_name}__isnull': True}).update(
                **{field_name: zero},
            )
    Employee.objects.filter(available_leave_balance__isnull=True).update(
        available_leave_balance=zero,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0024_alter_employeeledger_updated_at_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_null_decimals, migrations.RunPython.noop),
    ]
