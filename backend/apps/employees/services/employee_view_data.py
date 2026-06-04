"""تحميل بيانات صفحة عرض الموظف حسب التبويب النشط — تقليل الاستعلامات والذاكرة."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core.employee_tab_permissions import (
    employee_tab_visibility,
    resolve_default_employee_tab,
)
from apps.employees.models import Employee, EmployeeStatement

_STMT_COUNT_TYPES = ('statement', 'warning', 'final_warning', 'acknowledgment', 'other')

_EMPTY_FINGERPRINT = {
    'linked': False,
    'enrollments': [],
    'punches': [],
    'last_punch': None,
    'hidden_late_count': 0,
    'total_raw_count': 0,
    'displayed_count': 0,
    'truncated': False,
    'settings': None,
}


def resolve_active_employee_tab(user, requested_tab: str | None) -> str:
    return resolve_default_employee_tab(user, requested_tab)


def _needs_transfer_lists(active_tab: str, visible: dict[str, bool]) -> bool:
    """قوائم الفروع/الأقسام لنماذج النقل السريع."""
    if not visible.get('main'):
        return False
    return active_tab == 'main'


def load_employee_view_context(
    *,
    employee: Employee,
    user,
    active_tab: str,
    tab_visible: dict[str, bool],
    request_get,
) -> dict:
    """بيانات إضافية للقالب حسب التبويب — بعد جلب Employee بـ select_related."""
    from apps.core.models import Branch
    from apps.departments.models import Department
    from apps.employees.models import EmployeeCustody, EmployeeLedger

    ctx: dict = {
        'statements_count': 0,
        'next_statement_serial': EmployeeStatement.generate_serial('statement'),
        'schedule_boxes_json': [],
        'salary_adjusts': [],
        'custodies': [],
        'active_custodies': [],
        'business_trips': [],
        'loans': [],
        'absences': [],
        'contract_is_saudi': False,
        'contract_fourth_year_start': None,
        'accruals': [],
        'fingerprint_data': dict(_EMPTY_FINGERPRINT),
        'fp_date_from': '',
        'fp_date_to': '',
        'can_edit_biometric_settings': tab_visible.get('fingerprint', False),
        'departments': [],
        'branches': [],
    }

    if _needs_transfer_lists(active_tab, tab_visible):
        ctx['departments'] = list(Department.objects.order_by('name').only('id', 'name'))
        ctx['branches'] = list(
            Branch.objects.filter(is_deleted=False, is_active=True)
            .order_by('name')
            .only('id', 'name'),
        )

    if active_tab == 'warnings':
        ctx['statements_count'] = sum(
            1 for st in employee.statements_log.all()
            if st.statement_type in _STMT_COUNT_TYPES
        )

    if active_tab == 'salary':
        ctx['salary_adjusts'] = list(
            EmployeeStatement.objects.filter(
                employee_id=employee.pk,
                statement_type='salary_adjust',
            )
            .select_related('created_by')
            .order_by('-statement_date', '-created_at'),
        )

    if active_tab == 'schedule' and employee.work_schedule:
        try:
            data = json.loads(employee.work_schedule)
            if isinstance(data, dict) and isinstance(data.get('boxes'), list):
                ctx['schedule_boxes_json'] = data['boxes']
        except (ValueError, TypeError):
            pass

    if active_tab in ('custodies', 'main') or tab_visible.get('custodies'):
        active_qs = EmployeeCustody.objects.filter(
            employee_id=employee.pk, status='active',
        ).order_by('-received_at', '-id')
        ctx['active_custodies'] = list(active_qs)
        if active_tab == 'custodies':
            ctx['custodies'] = list(
                EmployeeCustody.objects.filter(employee_id=employee.pk)
                .order_by('-received_at', '-id'),
            )

    if active_tab == 'trips':
        ctx['business_trips'] = list(
            employee.business_trips.order_by('-start_date', '-id'),
        )

    if active_tab == 'loans':
        ctx['loans'] = list(employee.loans.all().order_by('-issued_at', '-id'))

    if active_tab == 'absences':
        ctx['absences'] = list(employee.absences.all().order_by('-absence_date', '-id'))

    if active_tab in ('contract', 'main'):
        from apps.employees.services.contract_rules import (
            fourth_year_start,
            is_saudi_nationality,
            sync_employee_contract,
        )
        if active_tab == 'contract':
            changed = sync_employee_contract(employee)
            if changed:
                employee.save(update_fields=[
                    'contract_type', 'contract_duration_months', 'contract_duration_text',
                    'contract_expiry_date',
                ])
        ctx['contract_is_saudi'] = is_saudi_nationality(employee.nationality)
        if ctx['contract_is_saudi'] and employee.hire_date:
            ctx['contract_fourth_year_start'] = fourth_year_start(employee.hire_date)

    if active_tab == 'accruals':
        ctx['accruals'] = _load_accruals_tab(employee, user)

    if active_tab == 'fingerprint' or request_get.get('fp_from') or request_get.get('fp_to'):
        ctx.update(_load_fingerprint_tab(employee, request_get))

    return ctx


def _load_accruals_tab(employee: Employee, user) -> list:
    from apps.employees.models import EmployeeLedger

    accruals_qs = employee.accruals_ledger.all().order_by('-date', '-created_at')
    if employee.hire_date and not accruals_qs.exists():
        _maybe_init_employee_ledger(employee, user)
    return list(
        employee.accruals_ledger.select_related('payroll_run')
        .order_by('-date', '-created_at'),
    )


def _maybe_init_employee_ledger(employee: Employee, user) -> None:
    from apps.employees.models import EmployeeLedger
    from apps.employees.services.accrual_ledger_notes import build_initial_balance_notes

    today = timezone.now().date()
    service_days = (today - employee.hire_date).days
    if service_days < 1:
        return

    service_years = Decimal(str(round(service_days / 365.25, 4)))
    leave_days = (Decimal(str(service_days)) * Decimal('21') / Decimal('365.25')).quantize(Decimal('0.01'))
    total_salary = Decimal(str(employee.total_salary or 0))
    daily_wage = (total_salary / Decimal('30')).quantize(Decimal('0.01'))
    leave_amount = (leave_days * daily_wage).quantize(Decimal('0.01'))

    half_salary = (total_salary / Decimal('2')).quantize(Decimal('0.01'))
    if service_years <= 5:
        eosb = (half_salary * service_years).quantize(Decimal('0.01'))
        eosb_detail = f'نصف الراتب × سنوات الخدمة = {half_salary} × {service_years} = {eosb}'
    else:
        first5 = (half_salary * Decimal('5')).quantize(Decimal('0.01'))
        extra_yrs = (service_years - Decimal('5')).quantize(Decimal('0.0001'))
        extra_amt = (total_salary * extra_yrs).quantize(Decimal('0.01'))
        eosb = (first5 + extra_amt).quantize(Decimal('0.01'))
        eosb_detail = (
            f'أول 5 سنوات: {half_salary} × 5 = {first5} | '
            f'بعد 5 سنوات: {total_salary} × {extra_yrs} = {extra_amt} | الإجمالي = {eosb}'
        )

    notes = build_initial_balance_notes(
        hire_date=employee.hire_date,
        as_of_date=today,
        total_salary=total_salary,
        leave_days=leave_days,
        leave_amount=leave_amount,
        eosb=eosb,
        eosb_detail=eosb_detail,
    )
    EmployeeLedger.objects.create(
        employee=employee,
        transaction_type='initial',
        date=today,
        leave_days_change=leave_days,
        leave_amount_change=leave_amount,
        eosb_amount_change=eosb,
        cumulative_leave_days=leave_days,
        cumulative_leave_amount=leave_amount,
        cumulative_eosb_amount=eosb,
        notes=notes,
        created_by=user,
    )


def _load_fingerprint_tab(employee: Employee, request_get) -> dict:
    from apps.attendance.services.employee_punch_display import (
        get_employee_punch_display,
        get_or_create_biometric_settings,
    )

    today = timezone.localdate()
    date_to = today
    date_from = today - timedelta(days=30)
    fp_from = request_get.get('fp_from')
    fp_to = request_get.get('fp_to')
    if fp_from:
        try:
            date_from = datetime.strptime(fp_from, '%Y-%m-%d').date()
        except ValueError:
            pass
    if fp_to:
        try:
            date_to = datetime.strptime(fp_to, '%Y-%m-%d').date()
        except ValueError:
            pass

    settings = get_or_create_biometric_settings(employee)
    fingerprint_data = get_employee_punch_display(
        employee,
        date_from=date_from,
        date_to=date_to,
        settings=settings,
        max_display=500,
    )
    fingerprint_data['settings'] = settings
    return {
        'fingerprint_data': fingerprint_data,
        'fp_date_from': date_from.isoformat(),
        'fp_date_to': date_to.isoformat(),
    }
