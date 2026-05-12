from django.contrib import admin
from .models import PayrollRun, PayrollLine


class PayrollLineInline(admin.TabularInline):
    model = PayrollLine
    extra = 0
    readonly_fields = ('employee', 'gross_salary', 'total_earnings',
                       'total_deductions', 'net_salary')
    fields = ('employee', 'gross_salary', 'absence_deduction', 'loan_deduction',
              'penalty_deduction', 'unpaid_leave_deduction', 'insurance_deduction',
              'total_earnings', 'total_deductions', 'net_salary')


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ('branch', 'period_year', 'period_month', 'status',
                    'employees_count', 'total_net', 'locked_at')
    list_filter = ('status', 'period_year', 'period_month', 'branch')
    search_fields = ('branch__name',)
    inlines = [PayrollLineInline]


@admin.register(PayrollLine)
class PayrollLineAdmin(admin.ModelAdmin):
    list_display = ('run', 'employee', 'gross_salary', 'total_deductions', 'net_salary')
    search_fields = ('employee__name',)
    list_filter = ('run__period_year', 'run__period_month', 'run__branch')
