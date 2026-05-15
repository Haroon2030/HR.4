# EmployeeLedger و HistoricalEmployeeLedger في 0020 يتضمنان أصلاً is_deleted و deleted_at.
# كانت 0021 السابقة تحاول إضافتهما مرة أخرى فتفشل على قواعد جديدة (duplicate column).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0020_employeeledger_historicalemployeeledger'),
    ]

    operations = []
