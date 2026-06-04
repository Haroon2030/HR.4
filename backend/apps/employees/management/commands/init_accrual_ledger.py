from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
from decimal import Decimal
from apps.employees.models import Employee, EmployeeLedger

class Command(BaseCommand):
    help = 'يهيئ سجل المخصصات والأرصدة (Ledger) للموظفين منذ تاريخ تعيينهم وحتى تاريخ اليوم.'

    def handle(self, *args, **options):
        employees = Employee.objects.filter(status__in=[Employee.Status.ACTIVE, Employee.Status.LEAVE])
        count = 0
        
        for emp in employees:
            if not emp.hire_date:
                continue
                
            # التحقق إذا كان الموظف يمتلك سجلاً مسبقاً
            if EmployeeLedger.objects.filter(employee=emp).exists():
                self.stdout.write(self.style.WARNING(f'الموظف {emp.name} لديه سجل مسبق. تخطّي.'))
                continue
                
            today = timezone.now().date()
            service_days = (today - emp.hire_date).days
            
            if service_days < 1:
                continue
                
            service_years = Decimal(str(round(service_days / 365.25, 4)))
            
            # حساب الإجازات المتراكمة حتى اليوم
            # 21 يوم في السنة = 21 / 365.25 يوم في اليوم الواحد
            leave_days = (service_days * Decimal('21') / Decimal('365.25')).quantize(Decimal('0.0001'))
            
            # في حال استخدم جزءاً منها، الرصيد المتبقي موجود في available_leave_balance
            # لكن إذا أردنا أن نبدأ برصيده الحالي الدقيق للإجازة، نأخذه من حقل available_leave_balance مباشرة
            current_leave_balance = Decimal(emp.available_leave_balance or 0)
            
            # حساب قيمة الإجازة بالريال
            from apps.core.salary_month import daily_rate_from_total
            daily_wage = daily_rate_from_total(emp.total_salary)
            leave_amount = (current_leave_balance * daily_wage).quantize(Decimal('0.01'))
            
            # حساب مخصص نهاية الخدمة المتراكم حتى اليوم
            eosb_amount = Decimal('0')
            last_salary = Decimal(emp.salary_for_end_of_service or 0)
            half_salary = (last_salary / Decimal('2')).quantize(Decimal('0.01'))
            
            if service_years <= 5:
                eosb_amount = (half_salary * service_years).quantize(Decimal('0.01'))
            else:
                first_5 = (half_salary * 5).quantize(Decimal('0.01'))
                extra_years = service_years - 5
                extra = (last_salary * extra_years).quantize(Decimal('0.01'))
                eosb_amount = first_5 + extra
                
            # إنشاء السجل الافتتاحي
            EmployeeLedger.objects.create(
                employee=emp,
                transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
                date=today,
                leave_days_change=current_leave_balance,
                leave_amount_change=leave_amount,
                eosb_amount_change=eosb_amount,
                cumulative_leave_days=current_leave_balance,
                cumulative_leave_amount=leave_amount,
                cumulative_eosb_amount=eosb_amount,
                notes=f'رصيد افتتاحي من تاريخ المباشرة ({emp.hire_date}) وحتى اليوم'
            )
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f'تمت التهيئة بنجاح لعدد {count} موظف.'))
