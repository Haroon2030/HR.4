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

    from apps.employees.services.migration_balance import employee_uses_migration_balance

    emp = get_object_or_404(Employee, id=employee_id)

    try:
        if employee_uses_migration_balance(emp):
            messages.warning(
                request,
                'الموظف مُرحّل بأرصدة افتتاحية — لا تستخدم تهيئة المباشرة. '
                'استخدم استيراد الأرصدة أو عدّل من المخصصات.',
            )
            return redirect('web:view_employee', employee_id=emp.id)

        if not emp.hire_date:
            messages.error(request, 'لا يمكن تهيئة الرصيد لموظف ليس له تاريخ مباشرة.')
            return redirect('web:view_employee', employee_id=emp.id)

        if EmployeeLedger.objects.filter(employee=emp).exists():
            messages.warning(request, 'الموظف لديه سجل مخصصات مسبق. لا يمكن تهيئته مرة أخرى.')
            return redirect('web:view_employee', employee_id=emp.id)

        from apps.core.salary_month import (
            accrued_annual_leave_days,
            daily_rate_from_total,
            employment_service_days,
            service_years_30day,
        )

        today = timezone.now().date()
        service_days = employment_service_days(emp.hire_date, today)

        if service_days < 1:
            messages.error(request, 'مدة الخدمة غير كافية لإنشاء مخصصات.')
            return redirect('web:view_employee', employee_id=emp.id)

        service_years = service_years_30day(service_days)
        leave_days = accrued_annual_leave_days(emp.hire_date, today)
        used_days = Decimal(emp.available_leave_balance or 0)
        remaining_days = max(leave_days - used_days, Decimal('0.00'))
        total_salary = Decimal(str(emp.total_salary or 0))
        eosb_base = Decimal(str(emp.salary_for_end_of_service or 0))

        daily_wage = daily_rate_from_total(total_salary)
        leave_amount = (remaining_days * daily_wage).quantize(Decimal('0.01'))

        eosb_amount = Decimal('0')
        if emp.sponsorship_id:
            half_salary = (eosb_base / Decimal('2')).quantize(Decimal('0.01'))

            if service_years <= 5:
                eosb_amount = (half_salary * service_years).quantize(Decimal('0.01'))
            else:
                first_5 = (half_salary * Decimal('5')).quantize(Decimal('0.01'))
                extra_years = service_years - Decimal('5')
                extra = (eosb_base * extra_years).quantize(Decimal('0.01'))
                eosb_amount = first_5 + extra

        from apps.employees.services.accrual_ledger_notes import build_initial_balance_notes

        notes = build_initial_balance_notes(
            hire_date=emp.hire_date,
            as_of_date=today,
            total_salary=total_salary,
            leave_days=remaining_days,
            leave_amount=leave_amount,
            eosb=eosb_amount,
            eosb_detail='من تاريخ المباشرة',
        )

        EmployeeLedger.objects.create(
            employee=emp,
            transaction_type='initial',
            date=today,
            leave_days_change=remaining_days,
            leave_amount_change=leave_amount,
            eosb_amount_change=eosb_amount,
            cumulative_leave_days=remaining_days,
            cumulative_leave_amount=leave_amount,
            cumulative_eosb_amount=eosb_amount,
            notes=notes,
            created_by=request.user,
        )

        messages.success(request, f'تمت تهيئة الرصيد الافتتاحي للموظف {emp.name} بنجاح.')
    except Exception as e:
        messages.error(request, f'خطأ في تهيئة الرصيد: {e}')

    return redirect('web:view_employee', employee_id=emp.id)
