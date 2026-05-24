"""إزالة حقول انتهاء الجواز والإقامة من الموظف وطلب التوظيف."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0025_backfill_null_salary_decimals'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='employee',
            name='passport_expiry_date',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='residency_expiry_date',
        ),
        migrations.RemoveField(
            model_name='employmentrequest',
            name='passport_expiry_date',
        ),
        migrations.RemoveField(
            model_name='employmentrequest',
            name='residency_expiry_date',
        ),
        migrations.RemoveField(
            model_name='historicalemployee',
            name='passport_expiry_date',
        ),
        migrations.RemoveField(
            model_name='historicalemployee',
            name='residency_expiry_date',
        ),
        migrations.RemoveField(
            model_name='historicalemploymentrequest',
            name='passport_expiry_date',
        ),
        migrations.RemoveField(
            model_name='historicalemploymentrequest',
            name='residency_expiry_date',
        ),
    ]
