"""تحميل بيانات صفحة عرض الموظف حسب التبويب النشط — تقليل الاستعلامات والذاكرة."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from apps.core.employee_tab_permissions import (
    employee_tab_visibility,
    resolve_default_employee_tab,
)
from apps.employees.models import Employee, EmployeeStatement

_STMT_COUNT_TYPES = ('statement', 'warning', 'final_warning', 'acknowledgment', 'other')

_EMPTY_FINGERPRINT = {
    'linked': False,
    'has_formal_enrollment': False,
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


def _tab_needed(
    tab_key: str,
    active_tab: str,
    visible: dict[str, bool],
    *,
    load_all_tabs: bool,
) -> bool:
    if not visible.get(tab_key):
        return False
    return load_all_tabs or active_tab == tab_key


def _needs_transfer_lists(
    active_tab: str,
    visible: dict[str, bool],
    *,
    load_all_tabs: bool,
) -> bool:
    """قوائم الفروع/الأقسام لنماذج النقل السريع."""
    return _tab_needed('main', active_tab, visible, load_all_tabs=load_all_tabs)


def load_employee_view_context(
    *,
    employee: Employee,
    user,
    active_tab: str,
    tab_visible: dict[str, bool],
    request_get,
    load_all_tabs: bool = True,
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
        'loans': [],
        'absences': [],
        'cash_shortages': [],
        'leave_timeline': [],
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

    need = lambda key: _tab_needed(key, active_tab, tab_visible, load_all_tabs=load_all_tabs)

    if _needs_transfer_lists(active_tab, tab_visible, load_all_tabs=load_all_tabs):
        ctx['departments'] = list(Department.objects.order_by('name').only('id', 'name'))
        ctx['branches'] = list(
            Branch.objects.filter(is_deleted=False, is_active=True)
            .order_by('name')
            .only('id', 'name'),
        )

    if need('warnings'):
        ctx['statements_count'] = sum(
            1 for st in employee.statements_log.all()
            if st.statement_type in _STMT_COUNT_TYPES
        )

    if need('salary'):
        ctx['salary_adjusts'] = list(
            EmployeeStatement.objects.filter(
                employee_id=employee.pk,
                statement_type='salary_adjust',
            )
            .select_related('created_by')
            .order_by('-statement_date', '-created_at'),
        )

    if need('schedule') and employee.work_schedule:
        try:
            data = json.loads(employee.work_schedule)
            if isinstance(data, dict) and isinstance(data.get('boxes'), list):
                ctx['schedule_boxes_json'] = data['boxes']
        except (ValueError, TypeError):
            pass

    if need('custodies') or need('main'):
        active_qs = EmployeeCustody.objects.filter(
            employee_id=employee.pk, status='active',
        ).order_by('-received_at', '-id')
        ctx['active_custodies'] = list(active_qs)
        if need('custodies'):
            ctx['custodies'] = list(
                EmployeeCustody.objects.filter(employee_id=employee.pk)
                .order_by('-received_at', '-id'),
            )

    if need('loans'):
        ctx['loans'] = list(employee.loans.all().order_by('-issued_at', '-id'))

    if need('absences'):
        absences = list(employee.absences.all().order_by('-absence_date', '-id'))
        ctx['absences'] = absences
        ctx['absences_days_total'] = sum((a.days or 0 for a in absences), 0)
        deduction_total = Decimal('0')
        for absence in absences:
            try:
                deduction_total += Decimal(str(absence.deduction_amount or 0))
            except (InvalidOperation, ValueError, TypeError):
                continue
        ctx['absences_deduction_total'] = deduction_total

    if need('cash_shortages'):
        shortages = list(
            employee.cash_shortages.select_related('branch', 'applied_to_payroll')
            .order_by('-shortage_date', '-id')
        )
        ctx['cash_shortages'] = shortages
        total_amount = Decimal('0')
        for row in shortages:
            try:
                total_amount += Decimal(str(row.amount or 0))
            except (InvalidOperation, ValueError, TypeError):
                continue
        ctx['cash_shortages_total'] = total_amount

    if need('leaves'):
        ctx['leave_timeline'] = _load_leave_timeline(employee)

    if need('contract') or need('main'):
        from apps.employees.services.contract_rules import (
            fourth_year_start,
            is_saudi_nationality,
            sync_employee_contract,
        )
        if need('contract'):
            changed = sync_employee_contract(employee)
            if changed:
                employee.save(update_fields=[
                    'contract_type', 'contract_duration_months', 'contract_duration_text',
                    'contract_expiry_date',
                ])
        ctx['contract_is_saudi'] = is_saudi_nationality(employee.nationality)
        if ctx['contract_is_saudi'] and employee.hire_date:
            ctx['contract_fourth_year_start'] = fourth_year_start(employee.hire_date)

    if need('accruals'):
        ctx['accruals'] = _load_accruals_tab(employee, user)

    if need('fingerprint') or request_get.get('fp_from') or request_get.get('fp_to'):
        ctx.update(_load_fingerprint_tab(employee, request_get))

    if need('archive'):
        from apps.employees.selectors.employee_archive import load_employee_archive_extras
        ctx.update(load_employee_archive_extras(employee=employee, user=user))

    ctx['employee_modal_js'] = _build_employee_modal_js(employee, user)

    return ctx


def _modal_js_float(value) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def _modal_js_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_employee_modal_js(employee: Employee, user) -> dict:
    """أرقام صفحة الموظف لـ Alpine — JSON آمن (نقطة عشرية) بعيداً عن تنسيق ar locale."""
    from apps.core.salary_access import user_can_view_salary

    hire = employee.hire_date
    payload = {
        'hire_date': hire.isoformat() if hire else '',
        'today_iso': timezone.localdate().isoformat(),
        'remaining_leave_days': _modal_js_float(employee.remaining_leave_days),
        'used_leave_days': _modal_js_float(employee.used_leave_days),
        'accrued_leave_days': _modal_js_float(employee.accrued_leave_days),
        'has_sponsor': bool(employee.sponsorship_id),
    }
    if user_can_view_salary(user):
        payload.update({
            'total_salary': _modal_js_float(employee.total_salary),
            'eos_salary': _modal_js_float(employee.salary_for_end_of_service),
            'meal_allowance': _modal_js_float(employee.meal_allowance),
            'basic_salary': _modal_js_float(employee.basic_salary),
            'housing_allowance': _modal_js_float(employee.housing_allowance),
            'transport_allowance': _modal_js_float(employee.transport_allowance),
            'other_allowance': _modal_js_float(employee.other_allowance),
            'cash_amount': _modal_js_float(employee.cash_amount),
        })
    return payload


def _user_display_name(user) -> str:
    if not user:
        return '—'
    return (user.get_full_name() or user.username or '—').strip() or '—'


def _parse_iso_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _load_leave_timeline(employee: Employee) -> list[dict]:
    """سجل الإجازات المُنفَّذة + طلبات الإجازة قيد الموافقة."""
    from apps.core.models import PendingAction
    from apps.employees.models import EmployeeLeave

    leave_labels = dict(EmployeeLeave.LeaveType.choices)
    rows: list[dict] = []

    for lv in (
        EmployeeLeave.objects.filter(employee_id=employee.pk)
        .select_related('created_by')
        .order_by('-date_from', '-created_at')
    ):
        search_bits = [
            lv.get_leave_type_display(),
            lv.notes or '',
            str(lv.date_from),
            str(lv.date_to),
            str(lv.days),
            _user_display_name(lv.created_by),
        ]
        rows.append({
            'sort_at': lv.created_at,
            'leave_type': lv.leave_type,
            'leave_type_display': lv.get_leave_type_display(),
            'date_from': lv.date_from,
            'date_to': lv.date_to,
            'days': lv.days,
            'notes': lv.notes or '',
            'executor_name': _user_display_name(lv.created_by),
            'status_label': 'مُسجَّلة',
            'status_class': 'bg-emerald-100 text-emerald-700',
            'document_url': lv.document.url if lv.document else '',
            'search_text': ' '.join(search_bits).lower(),
        })

    pending_qs = (
        PendingAction.objects.filter(
            employee_id=employee.pk,
            action_type=PendingAction.ActionType.LEAVE,
        )
        .exclude(status=PendingAction.Status.APPROVED)
        .select_related('requested_by')
        .order_by('-requested_at')
    )
    for action in pending_qs:
        payload = action.payload or {}
        leave_type = payload.get('leave_type') or EmployeeLeave.LeaveType.ANNUAL
        d_from = _parse_iso_date(payload.get('date_from'))
        d_to = _parse_iso_date(payload.get('date_to'))
        days = payload.get('days')
        if days in (None, ''):
            if d_from and d_to:
                days = (d_to - d_from).days + 1
            else:
                days = '—'
        type_display = leave_labels.get(leave_type, leave_type)
        search_bits = [
            type_display,
            payload.get('notes') or '',
            str(d_from or ''),
            str(d_to or ''),
            str(days),
            _user_display_name(action.requested_by),
            action.get_status_display(),
        ]
        status_class = 'bg-amber-100 text-amber-800'
        if action.status == PendingAction.Status.RETURNED:
            status_class = 'bg-rose-100 text-rose-700'
        rows.append({
            'sort_at': action.requested_at,
            'leave_type': leave_type,
            'leave_type_display': type_display,
            'date_from': d_from,
            'date_to': d_to,
            'days': days,
            'notes': payload.get('notes') or '',
            'executor_name': _user_display_name(action.requested_by),
            'status_label': action.get_status_display(),
            'status_class': status_class,
            'document_url': action.attachment.url if action.attachment else '',
            'search_text': ' '.join(search_bits).lower(),
        })

    rows.sort(key=lambda row: row['sort_at'] or timezone.now(), reverse=True)
    return rows


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

    from apps.core.salary_month import daily_rate_from_total, service_years_30day
    from apps.employees.services.leave_balance import (
        compute_employee_accrued_leave_days,
        employee_service_days,
    )

    today = timezone.now().date()
    service_days = employee_service_days(employee, as_of=today)
    if service_days < 1:
        return

    leave_days = compute_employee_accrued_leave_days(employee, as_of=today)
    service_years = service_years_30day(service_days)
    total_salary = Decimal(str(employee.total_salary or 0))
    daily_wage = daily_rate_from_total(total_salary)
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
