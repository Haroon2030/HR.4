# Generated manually for payroll transfer / detailed run support

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_branch_historicaluserprofile_branch_and_more'),
        ('employees', '0001_initial'),
        ('payroll', '0004_payrollrun_sponsorship'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='payrollrun',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='payrollrun',
            name='run_kind',
            field=models.CharField(
                choices=[('standard', 'مسير'), ('detailed', 'مسير تفصيلي')],
                db_index=True,
                default='standard',
                max_length=20,
                verbose_name='نوع المسير',
            ),
        ),
        migrations.AlterField(
            model_name='payrollrun',
            name='branch',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='payroll_runs',
                to='core.branch',
                verbose_name='الفرع',
            ),
        ),
        migrations.AddConstraint(
            model_name='payrollrun',
            constraint=models.UniqueConstraint(
                condition=models.Q(('run_kind', 'standard')),
                fields=('branch', 'period_year', 'period_month', 'salary_mode'),
                name='payroll_uniq_standard_run',
            ),
        ),
        migrations.AddConstraint(
            model_name='payrollrun',
            constraint=models.UniqueConstraint(
                condition=models.Q(('run_kind', 'detailed'), ('sponsorship__isnull', True)),
                fields=('company', 'period_year', 'period_month', 'salary_mode'),
                name='payroll_uniq_detailed_cash',
            ),
        ),
        migrations.AddConstraint(
            model_name='payrollrun',
            constraint=models.UniqueConstraint(
                condition=models.Q(('run_kind', 'detailed'), ('sponsorship__isnull', False)),
                fields=('company', 'period_year', 'period_month', 'salary_mode', 'sponsorship'),
                name='payroll_uniq_detailed_transfer',
            ),
        ),
        migrations.CreateModel(
            name='PayrollAllocationLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('transfer_date', models.DateField(blank=True, null=True, verbose_name='تاريخ النقل')),
                ('days_in_branch', models.DecimalField(decimal_places=1, default=0, max_digits=6, verbose_name='أيام في الفرع')),
                ('net_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='المبلغ على الفرع')),
                ('employee_net_total', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='صافي الموظف (كامل)')),
                ('bears_salary', models.BooleanField(db_index=True, default=False, verbose_name='يتحمل الراتب')),
                ('transfer_statement_id', models.PositiveIntegerField(blank=True, null=True, verbose_name='معرف سجل النقل')),
                ('notes', models.CharField(blank=True, max_length=255, verbose_name='ملاحظة')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payroll_allocations', to='core.branch', verbose_name='الفرع')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payroll_allocations', to='employees.employee', verbose_name='الموظف')),
                ('from_branch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='payroll_allocations_from', to='core.branch', verbose_name='من فرع')),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='allocation_lines', to='payroll.payrollrun', verbose_name='المسير التفصيلي')),
            ],
            options={
                'verbose_name': 'توزيع فرع — مسير تفصيلي',
                'verbose_name_plural': 'توزيعات الفروع — مسير تفصيلي',
                'ordering': ['employee__name', 'branch__name'],
                'indexes': [
                    models.Index(fields=['run', 'employee'], name='payroll_alloc_run_emp_idx'),
                    models.Index(fields=['run', 'branch'], name='payroll_alloc_run_br_idx'),
                ],
            },
        ),
    ]
