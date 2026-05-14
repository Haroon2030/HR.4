# Generated manually for EmployeeLedger model

import django.db.models.deletion
import django.utils.timezone
import simple_history.models
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0019_alter_employee_available_leave_balance_and_more'),
        ('payroll', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EmployeeLedger',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')),
                ('is_deleted', models.BooleanField(db_index=True, default=False, verbose_name='محذوف')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف')),
                ('transaction_type', models.CharField(choices=[('initial', 'رصيد افتتاحي (من المباشرة وحتى الآن)'), ('monthly', 'مخصص شهري (مسير رواتب)'), ('leave_taken', 'استخدام رصيد إجازة (خصم)'), ('settlement', 'تصفية نهائية (تصفير)'), ('adjustment', 'تسوية يدوية')], default='monthly', max_length=20, verbose_name='نوع الحركة')),
                ('date', models.DateField(default=django.utils.timezone.now, verbose_name='تاريخ الحركة')),
                ('leave_days_change', models.DecimalField(decimal_places=4, default=0, max_digits=8, verbose_name='التغير في أيام الإجازة')),
                ('leave_amount_change', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='التغير في قيمة الإجازة')),
                ('eosb_amount_change', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='التغير في قيمة نهاية الخدمة')),
                ('cumulative_leave_days', models.DecimalField(decimal_places=4, default=0, max_digits=8, verbose_name='رصيد أيام الإجازة المتراكم')),
                ('cumulative_leave_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='رصيد قيمة الإجازة المتراكم')),
                ('cumulative_eosb_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='رصيد نهاية الخدمة المتراكم')),
                ('notes', models.TextField(blank=True, verbose_name='ملاحظات / تفاصيل الحساب')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='accruals_ledger', to='employees.employee', verbose_name='الموظف')),
                ('payroll_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ledger_entries', to='payroll.payrollrun', verbose_name='مسير الرواتب المرتبط')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='أُضيفت بواسطة')),
            ],
            options={
                'verbose_name': 'سجل مخصصات موظف',
                'verbose_name_plural': 'سجلات مخصصات الموظفين',
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='HistoricalEmployeeLedger',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('created_at', models.DateTimeField(blank=True, editable=False, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(blank=True, editable=False, verbose_name='آخر تحديث')),
                ('is_deleted', models.BooleanField(db_index=True, default=False, verbose_name='محذوف')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف')),
                ('transaction_type', models.CharField(choices=[('initial', 'رصيد افتتاحي (من المباشرة وحتى الآن)'), ('monthly', 'مخصص شهري (مسير رواتب)'), ('leave_taken', 'استخدام رصيد إجازة (خصم)'), ('settlement', 'تصفية نهائية (تصفير)'), ('adjustment', 'تسوية يدوية')], default='monthly', max_length=20, verbose_name='نوع الحركة')),
                ('date', models.DateField(default=django.utils.timezone.now, verbose_name='تاريخ الحركة')),
                ('leave_days_change', models.DecimalField(decimal_places=4, default=0, max_digits=8, verbose_name='التغير في أيام الإجازة')),
                ('leave_amount_change', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='التغير في قيمة الإجازة')),
                ('eosb_amount_change', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='التغير في قيمة نهاية الخدمة')),
                ('cumulative_leave_days', models.DecimalField(decimal_places=4, default=0, max_digits=8, verbose_name='رصيد أيام الإجازة المتراكم')),
                ('cumulative_leave_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='رصيد قيمة الإجازة المتراكم')),
                ('cumulative_eosb_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='رصيد نهاية الخدمة المتراكم')),
                ('notes', models.TextField(blank=True, verbose_name='ملاحظات / تفاصيل الحساب')),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('created_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='أُضيفت بواسطة')),
                ('employee', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='employees.employee', verbose_name='الموظف')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('payroll_run', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='payroll.payrollrun', verbose_name='مسير الرواتب المرتبط')),
            ],
            options={
                'verbose_name': 'historical سجل مخصصات موظف',
                'verbose_name_plural': 'historical سجلات مخصصات الموظفين',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
        ),
    ]
