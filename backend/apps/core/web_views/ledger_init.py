from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.decorators import permission_required

@login_required
@permission_required('employees.edit')
def run_ledger_init(request, employee_id):
    from apps.employees.models import Employee, EmployeeLedger
    from django.utils import timezone
    from decimal import Decimal
    from django.contrib import messages
    from django.shortcuts import redirect

    emp = get_object_or_404(Employee, id=employee_id)
    
    if not emp.hire_date:
        messages.error(request, 'لا يمكن تهيئة الرصيد لموظف ليس له تاريخ مباشرة.')
        return redirect('web:view_employee', employee_id=emp.id)
        
    if EmployeeLedger.objects.filter(employee=emp).exists():
        messages.warning(request, 'الموظف لديه سجل مخصصات مسبق. لا يمكن تهيئته مرة أخرى لتجنب التكرار.')
        return redirect('web:view_employee', employee_id=emp.id)

    today = timezone.now().date()
    service_days = (today - emp.hire_date).days
    
    if service_days < 1:
        messages.error(request, 'مدة الخدمة غير كافية لإنشاء مخصصات.')
        return redirect('web:view_employee', employee_id=emp.id)
        
    service_years = Decimal(str(round(service_days / 365.25, 4)))
    
    # حساب الإجازات المتراكمة حتى اليوم
    # 21 يوم في السنة
    leave_days = (service_days * Decimal('21') / Decimal('365.25')).quantize(Decimal('0.0001'))
    current_leave_balance = Decimal(emp.available_leave_balance or 0)
    
    daily_wage = (Decimal(emp.total_salary or 0) / Decimal('30')).quantize(Decimal('0.01'))
    leave_amount = (current_leave_balance * daily_wage).quantize(Decimal('0.01'))
    
    # حساب نهاية الخدمة
    eosb_amount = Decimal('0')
    last_salary = Decimal(emp.total_salary or 0)
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
        leave_days_change=current_leave_balance,
        leave_amount_change=leave_amount,
        eosb_amount_change=eosb_amount,
        cumulative_leave_days=current_leave_balance,
        cumulative_leave_amount=leave_amount,
        cumulative_eosb_amount=eosb_amount,
        notes=f'رصيد افتتاحي من تاريخ المباشرة ({emp.hire_date}) وحتى اليوم',
        created_by=request.user
    )
    
    messages.success(request, f'تمت تهيئة الرصيد الافتتاحي للموظف {emp.name} بنجاح.')
    return redirect('web:view_employee', employee_id=emp.id)
