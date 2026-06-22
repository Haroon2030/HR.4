from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.salary_month import (
    accrued_annual_leave_days,
    daily_rate_from_total,
    employment_service_days,
    service_years_30day,
)
from apps.employees.models import Employee, EmployeeLedger


class Command(BaseCommand):
    help = 'يهيئ سجل المخصصات والأرصدة (Ledger) للموظفين منذ تاريخ تعيينهم وحتى تاريخ اليوم.'

    def handle(self, *args, **options):
        employees = Employee.objects.filter(status__in=[Employee.Status.ACTIVE, Employee.Status.LEAVE])
        count = 0

        for emp in employees:
            if not emp.hire_date:
                continue

            if EmployeeLedger.objects.filter(employee=emp).exists():
                self.stdout.write(self.style.WARNING(f'الموظف {emp.name} لديه سجل مسبق. تخطّي.'))
                continue

            today = timezone.now().date()
            service_days = employment_service_days(emp.hire_date, today)

            if service_days < 1:
                continue

            service_years = service_years_30day(service_days)
            leave_days = accrued_annual_leave_days(emp.hire_date, today)
            used_days = Decimal(emp.available_leave_balance or 0)
            remaining_days = max(leave_days - used_days, Decimal('0.00'))

            daily_wage = daily_rate_from_total(emp.total_salary)
            leave_amount = (remaining_days * daily_wage).quantize(Decimal('0.01'))

            eosb_amount = Decimal('0')
            if emp.sponsorship_id:
                last_salary = Decimal(emp.salary_for_end_of_service or 0)
                half_salary = (last_salary / Decimal('2')).quantize(Decimal('0.01'))

                if service_years <= 5:
                    eosb_amount = (half_salary * service_years).quantize(Decimal('0.01'))
                else:
                    first_5 = (half_salary * 5).quantize(Decimal('0.01'))
                    extra_years = service_years - 5
                    extra = (last_salary * extra_years).quantize(Decimal('0.01'))
                    eosb_amount = first_5 + extra

            EmployeeLedger.objects.create(
                employee=emp,
                transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
                date=today,
                leave_days_change=remaining_days,
                leave_amount_change=leave_amount,
                eosb_amount_change=eosb_amount,
                cumulative_leave_days=remaining_days,
                cumulative_leave_amount=leave_amount,
                cumulative_eosb_amount=eosb_amount,
                notes=f'رصيد افتتاحي من تاريخ المباشرة ({emp.hire_date}) وحتى اليوم',
            )
            count += 1

        self.stdout.write(self.style.SUCCESS(f'تمت التهيئة بنجاح لعدد {count} موظف.'))
