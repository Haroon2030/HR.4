from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.core.decorators import permission_required
from apps.core.web_views._helpers import employee_branch_access_required


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def run_ledger_init(request, employee_id):
    from apps.employees.models import Employee, EmployeeLedger
    from django.utils import timezone
    from decimal import Decimal
    import traceback

    emp = get_object_or_404(Employee, id=employee_id)

    try:
        if not emp.hire_date:
            messages.error(request, 'لا يمكن تهيئة الرصيد لموظف ليس له تاريخ مباشرة.')
            return redirect('web:view_employee', employee_id=emp.id)

        if EmployeeLedger.objects.filter(employee=emp).exists():
            messages.warning(request, 'الموظف لديه سجل مخصصات مسبق. لا يمكن تهيئته مرة أخرى.')
            return redirect('web:view_employee', employee_id=emp.id)

        today = timezone.now().date()
        service_days = (today - emp.hire_date).days

        if service_days < 1:
            messages.error(request, 'مدة الخدمة غير كافية لإنشاء مخصصات.')
            return redirect('web:view_employee', employee_id=emp.id)

        service_years = Decimal(str(round(service_days / 365.25, 4)))

        # حساب أيام الإجازة المتراكمة: 21 يوم في السنة من تاريخ المباشرة
        leave_days = (Decimal(str(service_days)) * Decimal('21') / Decimal('365.25')).quantize(Decimal('0.01'))
        total_salary = Decimal(str(emp.total_salary or 0))
        eosb_base = Decimal(str(emp.salary_for_end_of_service or 0))

        from apps.core.salary_month import daily_rate_from_total
        daily_wage = daily_rate_from_total(total_salary)
        leave_amount = (leave_days * daily_wage).quantize(Decimal('0.01'))

        # مكافأة نهاية الخدمة — بدون بدل التغذية
        half_salary = (eosb_base / Decimal('2')).quantize(Decimal('0.01'))

        if service_years <= 5:
            eosb_amount = (half_salary * service_years).quantize(Decimal('0.01'))
        else:
            first_5 = (half_salary * Decimal('5')).quantize(Decimal('0.01'))
            extra_years = service_years - Decimal('5')
            extra = (eosb_base * extra_years).quantize(Decimal('0.01'))
            eosb_amount = first_5 + extra

        EmployeeLedger.objects.create(
            employee=emp,
            transaction_type='initial',
            date=today,
            leave_days_change=leave_days,
            leave_amount_change=leave_amount,
            eosb_amount_change=eosb_amount,
            cumulative_leave_days=leave_days,
            cumulative_leave_amount=leave_amount,
            cumulative_eosb_amount=eosb_amount,
            notes=f'رصيد افتتاحي من تاريخ المباشرة ({emp.hire_date}) وحتى اليوم',
            created_by=request.user
        )

        messages.success(request, f'تمت تهيئة الرصيد الافتتاحي للموظف {emp.name} بنجاح.')
    except Exception as e:
        messages.error(request, f'خطأ في تهيئة الرصيد: {e}')

    return redirect('web:view_employee', employee_id=emp.id)
