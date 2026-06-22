"""
خدمة تنفيذ الطلبات المعلّقة — Pending Actions Executor
=======================================================
هذا الملف يُنفَّذ تلقائياً عند وصول PendingAction لحالة APPROVED.

لكل نوع طلب (ActionType) يوجد دالة executor مسؤولة عن:
  - تطبيق التغيير الفعلي على الموظف (تحديث قاعدة البيانات)
  - تسجيل إفادة (EmployeeStatement) للتوثيق
  - حساب المستحقات أو الخصومات إن وجدت

أنواع الطلبات المدعومة:
  ├── LEAVE           → تسجيل إجازة + تحديث الرصيد
  ├── TERMINATE       → تصفية الموظف + تسجيل نهاية الخدمة
  ├── REACTIVATE      → إعادة تفعيل موظف مُصفّى
  ├── SALARY_ADJUST   → تعديل الراتب الأساسي
  ├── TRANSFER        → نقل الموظف لفرع/قسم آخر
  ├── CUSTODY_RECEIVE → تسجيل استلام عهدة
  ├── CUSTODY_CLEAR   → تصفية عهدة مُستلمة
  ├── BUSINESS_TRIP   → تسجيل رحلة عمل
  ├── LOAN_REQUEST    → إنشاء سلفة + أقساط شهرية
  └── ABSENCE         → تسجيل غياب + حساب الخصم
  └── CASH_SHORTAGE   → تسجيل عجز كاشير + خصم من الراتب

كل دالة مغلّفة بـ @transaction.atomic لضمان عدم وجود بيانات جزئية.
الدالة الرئيسية: execute_pending_action(action, user) — تستدعي المنفّذ المناسب.
"""
import json
import os
from datetime import date
from decimal import Decimal
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from apps.core.salary_month import daily_rate_from_total
from apps.core.services.approval_routing import notify_on_first_stage, resolve_first_approver, snapshot_routing_fields


def _to_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _to_decimal(value):
    return Decimal(str(value))


# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def _execute_leave(action, executor):
    from apps.employees.models import EmployeeLeave
    p = action.payload
    employee = action.employee

    # ── تحقق: الإجازة السنوية تتطلب كفالة ──
    leave_type = p.get('leave_type', EmployeeLeave.LeaveType.ANNUAL)
    if leave_type == EmployeeLeave.LeaveType.ANNUAL and not employee.sponsorship_id:
        raise ValueError('لا يمكن تسجيل إجازة سنوية: الموظف غير مُسجَّل على كفالة.')

    d_from = _to_date(p['date_from'])
    d_to = _to_date(p['date_to'])
    if d_to < d_from:
        raise ValueError('تاريخ نهاية الإجازة يجب أن يكون بعد البداية.')
    days = Decimal((d_to - d_from).days + 1)

    EmployeeLeave.objects.create(
        employee=employee,
        leave_type=leave_type,
        date_from=d_from,
        date_to=d_to,
        days=days,
        notes=p.get('notes', ''),
        document=action.attachment or None,
        created_by=action.requested_by,
    )

    if leave_type == EmployeeLeave.LeaveType.ANNUAL:
        employee.available_leave_balance = (
            Decimal(employee.available_leave_balance or 0) + days
        )
        employee.save(update_fields=['available_leave_balance'])

        # ── إنشاء سجل في المخصصات (خصم الإجازة من الرصيد التراكمي) ──
        from apps.employees.models import EmployeeLedger
        last_ledger = EmployeeLedger.objects.filter(employee=employee).order_by('-date', '-created_at').first()
        prev_leave_days = last_ledger.cumulative_leave_days if last_ledger else Decimal('0')
        prev_leave_amt = last_ledger.cumulative_leave_amount if last_ledger else Decimal('0')
        prev_eosb = last_ledger.cumulative_eosb_amount if last_ledger else Decimal('0')

        daily_wage = daily_rate_from_total(employee.total_salary)
        leave_amount_deducted = (days * daily_wage).quantize(Decimal('0.01'))

        EmployeeLedger.objects.create(
            employee=employee,
            transaction_type=EmployeeLedger.TransactionType.LEAVE_TAKEN,
            date=timezone.now().date(),
            leave_days_change=-days,
            leave_amount_change=-leave_amount_deducted,
            eosb_amount_change=Decimal('0'),
            cumulative_leave_days=prev_leave_days - days,
            cumulative_leave_amount=prev_leave_amt - leave_amount_deducted,
            cumulative_eosb_amount=prev_eosb,
            notes=f'استخدام إجازة: {days} يوم',
            created_by=executor
        )

    return f'تم تسجيل إجازة ({days} يوم) للموظف {employee.name}'


# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def _execute_terminate(action, executor):
    from apps.employees.models import Employee, EmployeeStatement
    p = action.payload
    employee = action.employee

    end_date = _to_date(p['end_date'])
    end_reason = p.get('end_reason', '')

    employee.end_date = end_date
    employee.end_reason = end_reason
    employee.status = Employee.Status.TERMINATED
    employee.save(update_fields=['end_date', 'end_reason', 'status'])

    from apps.payroll.services.settlement_payroll import remove_employee_from_draft_payroll_runs

    payroll_cleanup = remove_employee_from_draft_payroll_runs(employee)

    comp_text = (
        f'بدل الإجازة المستحق: {employee.leave_compensation} ر.س'
        if employee.sponsorship_id
        else 'لا يوجد كفالة — لم تُحتسب مستحقات'
    )
    EmployeeStatement.objects.create(
        employee=employee,
        statement_type=EmployeeStatement.StatementType.TERMINATE,
        title='تصفية الموظف',
        statement_date=end_date,
        content=(
            f'تاريخ انتهاء الخدمة: {end_date}\n'
            f'السبب: {end_reason or "—"}\n'
            f'{comp_text}'
        ),
        created_by=action.requested_by,
    )
    removed = payroll_cleanup.get('lines_removed', 0) + payroll_cleanup.get('allocations_removed', 0)
    suffix = f' (أُزيل من {removed} سطر مسير مسودة)' if removed else ''
    return f'تمت تصفية {employee.name} بتاريخ {end_date}{suffix}'


# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def _execute_reactivate(action, executor):
    from apps.employees.models import Employee, EmployeeStatement
    p = action.payload
    employee = action.employee

    new_hire_date = _to_date(p['new_hire_date'])
    reason = p.get('reactivation_reason', '')
    new_status = p.get('new_status', Employee.Status.ACTIVE)
    if new_status not in (Employee.Status.ACTIVE, Employee.Status.LEAVE):
        new_status = Employee.Status.ACTIVE

    old_end_date = employee.end_date
    old_end_reason = employee.end_reason

    employee.hire_date = new_hire_date
    employee.end_date = None
    employee.end_reason = ''
    employee.status = new_status
    employee.available_leave_balance = 0
    employee.save(update_fields=[
        'hire_date', 'end_date', 'end_reason', 'status', 'available_leave_balance'
    ])

    EmployeeStatement.objects.create(
        employee=employee,
        statement_type=EmployeeStatement.StatementType.REACTIVATE,
        title='إعادة تفعيل الموظف',
        statement_date=new_hire_date,
        content=(
            f'تمت إعادة تفعيل الموظف بتاريخ {new_hire_date}.\n'
            f'السبب: {reason}\n'
            f'بيانات التصفية السابقة — تاريخ الانتهاء: {old_end_date or "—"}، '
            f'السبب: {old_end_reason or "—"}'
        ),
        created_by=action.requested_by,
    )
    return f'تمت إعادة تفعيل {employee.name}'


# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def _execute_salary_adjust(action, executor):
    from apps.employees.models import EmployeeStatement
    p = action.payload
    employee = action.employee

    new_basic = _to_decimal(p['new_basic_salary'])
    reason = p.get('reason', '')
    effective_date = _to_date(p['effective_date'])

    old_basic = employee.basic_salary
    old_total = employee.total_salary

    employee.basic_salary = new_basic
    employee.save(update_fields=['basic_salary'])

    new_total = employee.total_salary
    diff = new_total - old_total
    pct = (diff / old_total * 100).quantize(Decimal('0.1')) if old_total else Decimal('0.0')
    direction = 'زيادة' if diff > 0 else ('خفض' if diff < 0 else 'بدون تغيير')

    EmployeeStatement.objects.create(
        employee=employee,
        statement_type=EmployeeStatement.StatementType.SALARY_ADJUST,
        title=f'تعديل راتب — {direction}',
        statement_date=effective_date,
        content=(
            f'تاريخ التعديل: {effective_date}\n'
            f'السبب: {reason}\n'
            f'───────────────────\n'
            f'الراتب الأساسي:  {old_basic}  ←  {new_basic}  ر.س\n'
            f'الإجمالي السابق: {old_total}  ر.س\n'
            f'الإجمالي الجديد: {new_total}  ر.س\n'
            f'الفرق: {diff:+}  ر.س  ({pct:+}%)'
        ),
        created_by=action.requested_by,
    )
    return f'تم تعديل راتب {employee.name} ({direction})'


# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def _execute_transfer(action, executor):
    from apps.employees.models import EmployeeStatement
    from apps.core.models import Branch
    from apps.departments.models import Department
    p = action.payload
    employee = action.employee

    transfer_date = _to_date(p['transfer_date'])
    reason = p.get('reason', '')
    new_branch = Branch.objects.filter(id=p.get('new_branch_id')).first() if p.get('new_branch_id') else None
    new_dept = Department.objects.filter(id=p.get('new_department_id')).first() if p.get('new_department_id') else None

    old_branch = employee.branch
    old_dept = employee.department

    changed = []
    if new_branch and new_branch != old_branch:
        employee.branch = new_branch
        changed.append('branch')
    if new_dept and new_dept != old_dept:
        employee.department = new_dept
        changed.append('department')

    if changed:
        employee.save(update_fields=changed)

    data = {
        'type': 'transfer',
        'reason': reason,
        'branch_from': old_branch.name if old_branch else '—',
        'branch_to': new_branch.name if new_branch else '—',
        'branch_from_id': old_branch.id if old_branch else None,
        'branch_to_id': new_branch.id if new_branch else None,
        'dept_from': old_dept.name if old_dept else '—',
        'dept_to': new_dept.name if new_dept else '—',
        'branch_changed': 'branch' in changed,
        'dept_changed': 'department' in changed,
    }
    EmployeeStatement.objects.create(
        employee=employee,
        statement_type=EmployeeStatement.StatementType.TRANSFER,
        title='نقل موظف',
        statement_date=transfer_date,
        content=json.dumps(data, ensure_ascii=False),
        created_by=action.requested_by,
    )
    return f'تم نقل {employee.name}'


# ─────────────────────────────────────────────────────────────────────────────
EXECUTORS = {
    'leave': _execute_leave,
    'terminate': _execute_terminate,
    'reactivate': _execute_reactivate,
    'salary_adjust': _execute_salary_adjust,
    'transfer': _execute_transfer,
    'custody_receive': None,  # ملحقة أدناه بعد التعريف
    'custody_clear': None,
    'business_trip': None,
}


def _build_form_serial_local(code, employee_id):
    """مولّد سريال موحّد مع _build_form_serial في hr_forms.py"""
    import hashlib
    from datetime import datetime
    now = datetime.now()
    date_part = now.strftime('%y%m%d')
    emp_part = f"{int(employee_id):04d}"
    raw = f"{code}-{employee_id}-{now.strftime('%Y%m%d%H%M%S%f')}"
    hash_part = hashlib.sha1(raw.encode()).hexdigest()[:4].upper()
    return f"{code}-{date_part}-{emp_part}-{hash_part}"


def _copy_pending_attachment(attachment):
    """نسخ مرفق الطلب المعلّق إلى حقل مستند جديد (مسار upload_to الصحيح)."""
    if not attachment:
        return None
    attachment.open('rb')
    try:
        data = attachment.read()
    finally:
        attachment.close()
    return ContentFile(data, name=os.path.basename(attachment.name))


@transaction.atomic
def _execute_custody_receive(action, executor):
    from apps.employees.models import EmployeeCustody
    p = action.payload
    employee = action.employee
    serial = p.get('serial_number') or _build_form_serial_local('CR', employee.id)
    custody = EmployeeCustody.objects.create(
        employee=employee,
        serial_number=serial,
        item_name=p['item_name'],
        item_details=p.get('item_details', ''),
        quantity=int(p.get('quantity', 1)),
        estimated_value=_to_decimal(p['estimated_value']) if p.get('estimated_value') not in (None, '') else None,
        received_at=_to_date(p['received_at']),
        notes=p.get('notes', ''),
        document=action.attachment or None,
        status=EmployeeCustody.Status.ACTIVE,
        created_by=action.requested_by,
    )
    return f'تم تسجيل استلام عهدة "{custody.item_name}" للموظف {employee.name}'


@transaction.atomic
def _execute_custody_clear(action, executor):
    from apps.employees.models import EmployeeCustody
    p = action.payload
    employee = action.employee
    custody = EmployeeCustody.objects.filter(
        id=p.get('custody_id'), employee=employee, status=EmployeeCustody.Status.ACTIVE
    ).first()
    if not custody:
        raise ValueError('العهدة غير موجودة أو سبق تصفيتها.')
    custody.status = EmployeeCustody.Status.RETURNED
    custody.returned_at = _to_date(p['returned_at'])
    custody.return_notes = p.get('return_notes', '')
    if action.attachment:
        custody.return_document = action.attachment
    custody.save(update_fields=['status', 'returned_at', 'return_notes', 'return_document'])
    return f'تم تصفية عهدة "{custody.item_name}" من الموظف {employee.name}'


@transaction.atomic
def _execute_business_trip(action, executor):
    from apps.employees.models import EmployeeBusinessTrip
    p = action.payload
    employee = action.employee
    serial = p.get('serial_number') or _build_form_serial_local('BT', employee.id)
    trip = EmployeeBusinessTrip.objects.create(
        employee=employee,
        serial_number=serial,
        destination=p['destination'],
        purpose=p['purpose'],
        start_date=_to_date(p['start_date']),
        end_date=_to_date(p['end_date']),
        estimated_cost=_to_decimal(p['estimated_cost']) if p.get('estimated_cost') not in (None, '') else None,
        notes=p.get('notes', ''),
        document=action.attachment or None,
        created_by=action.requested_by,
    )
    return f'تم تسجيل رحلة عمل إلى {trip.destination} للموظف {employee.name}'


@transaction.atomic
def _execute_loan_request(action, executor):
    from apps.employees.models import EmployeeLoan
    p = action.payload
    employee = action.employee
    serial = p.get('serial_number') or _build_form_serial_local('LN', employee.id)
    loan = EmployeeLoan.objects.create(
        employee=employee,
        serial_number=serial,
        amount=_to_decimal(p['amount']),
        monthly_deduction=_to_decimal(p['monthly_deduction']),
        installments=int(p.get('installments') or 1),
        reason=p.get('reason', ''),
        issued_at=_to_date(p['issued_at']),
        first_deduction_date=_to_date(p['first_deduction_date']) if p.get('first_deduction_date') else None,
        notes=p.get('notes', ''),
        document=action.attachment or None,
        created_by=action.requested_by,
    )
    loan.generate_installments()
    return f'تم صرف سلفة بمبلغ {loan.amount} للموظف {employee.name}'


@transaction.atomic
def _execute_absence(action, executor):
    from apps.employees.models import EmployeeAbsence
    from decimal import Decimal
    from apps.core.salary_month import daily_rate_from_total, salary_month_days

    p = action.payload
    employee = action.employee
    serial = p.get('serial_number') or _build_form_serial_local('AB', employee.id)
    absence_date = _to_date(p['absence_date'])
    days = int(p.get('days') or 1)
    month_days = salary_month_days()
    total_salary = Decimal(employee.total_salary or 0)
    daily_rate = daily_rate_from_total(total_salary)
    deduction = (daily_rate * Decimal(days)).quantize(Decimal('0.01'))
    absence = EmployeeAbsence.objects.create(
        employee=employee,
        serial_number=serial,
        absence_date=absence_date,
        days=days,
        month_days=month_days,
        total_salary_snapshot=total_salary,
        daily_rate=daily_rate,
        deduction_amount=deduction,
        reason=p.get('reason', ''),
        notes=p.get('notes', ''),
        document=action.attachment or None,
        created_by=action.requested_by,
    )
    return (f'تم تسجيل غياب {absence.days} يوم للموظف {employee.name} '
            f'(سعر اليوم {daily_rate} × {days} = خصم {deduction} ر.س)')


@transaction.atomic
def _execute_cash_shortage(action, executor):
    from apps.core.models import Branch
    from apps.employees.models import EmployeeCashShortage

    p = action.payload
    employee = action.employee
    serial = p.get('serial_number') or _build_form_serial_local('CS', employee.id)
    branch_id = p.get('branch_id')
    branch = Branch.objects.filter(id=branch_id).first() if branch_id else employee.branch
    if not branch:
        raise ValueError('الفرع مطلوب لتسجيل عجز الكاشير.')
    amount = _to_decimal(p['amount'])
    shortage = EmployeeCashShortage.objects.create(
        employee=employee,
        serial_number=serial,
        shortage_date=_to_date(p['shortage_date']),
        amount=amount,
        branch=branch,
        notes=p.get('notes', ''),
        document=_copy_pending_attachment(action.attachment),
        created_by=action.requested_by,
    )
    return f'تم تسجيل عجز كاشير بمبلغ {shortage.amount} ر.س للموظف {employee.name}'


EXECUTORS['custody_receive'] = _execute_custody_receive
EXECUTORS['custody_clear'] = _execute_custody_clear
EXECUTORS['business_trip'] = _execute_business_trip
EXECUTORS['loan_request'] = _execute_loan_request
EXECUTORS['absence'] = _execute_absence
EXECUTORS['cash_shortage'] = _execute_cash_shortage


# ─────────────────────────────────────────────────────────────────────────────
# تصفية نهاية خدمة أو استقالة
# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def _execute_end_of_service(action, executor):
    from apps.employees.models import Employee, EmployeeStatement

    p = action.payload
    employee = action.employee
    end_date = _to_date(p['end_date'])
    settlement_type = p.get('terminated_by', 'company')
    article_party = p.get('article_party') or p.get('article_77_party', '')
    end_reason = p.get('end_reason', '')
    notes = p.get('notes', '')

    hire_date = employee.hire_date
    if not hire_date:
        raise ValueError('لا يوجد تاريخ مباشرة للموظف — لا يمكن حساب المكافأة.')

    from apps.core.salary_month import employment_service_days, service_years_30day

    service_days = employment_service_days(hire_date, end_date)
    if service_days < 1:
        raise ValueError('تاريخ التصفية يجب أن يكون بعد تاريخ المباشرة.')
    service_years = service_years_30day(service_days)

    last_salary = Decimal(employee.salary_for_end_of_service or 0)
    total_salary = Decimal(employee.total_salary or 0)
    from apps.employees.services.settlement_eosb import (
        ARTICLE_77_PENALTY_MONTHS,
        LEAVE_ONLY_SETTLEMENTS,
        compute_article_80_leave_settlement,
        compute_probation_end_leave_settlement,
        compute_settlement_eosb,
        compute_two_month_penalty,
        resolve_eosb_settlement_type,
        settlement_type_label,
    )

    eosb_before, eosb, category, resignation_note = compute_settlement_eosb(
        last_salary=last_salary,
        service_days=service_days,
        service_years=service_years,
        settlement_type=settlement_type,
        eligible=bool(employee.sponsorship_id),
        article_party=article_party,
    )

    penalty = Decimal('0.00')
    if settlement_type == 'article_77':
        penalty = compute_two_month_penalty(total_salary)

    if settlement_type in LEAVE_ONLY_SETTLEMENTS:
        leave_fn = (
            compute_probation_end_leave_settlement
            if settlement_type == 'probation_end'
            else compute_article_80_leave_settlement
        )
        leave_days, leave_comp, leave_text = leave_fn(
            employee=employee,
            as_of=end_date,
        )
    else:
        from apps.employees.services.leave_balance import settlement_leave_for_employee

        _, _, leave_days, leave_comp, leave_text = settlement_leave_for_employee(
            employee,
            as_of=end_date,
        )

    total_entitlement = eosb + leave_comp + penalty

    type_label = settlement_type_label(settlement_type, article_party=article_party)
    if settlement_type == 'contract_expiry':
        default_reason = 'انتهاء العقد بانتهاء مدته'
    elif settlement_type == 'article_74':
        default_reason = 'إنهاء العقد بالتراضي (المادة 74)'
    elif settlement_type == 'article_77':
        default_reason = 'إنهاء العقد — سبب غير مشروع (المادة 77)'
    elif settlement_type == 'article_80':
        default_reason = 'إنهاء العقد — سبب مشروع (المادة 80)'
    elif settlement_type == 'probation_end':
        default_reason = 'إنهاء العقد — نهاية فترة التجربة'
    elif settlement_type == 'employee':
        default_reason = 'استقالة'
    else:
        default_reason = 'تصفية نهاية خدمة'

    employee.end_date = end_date
    employee.end_reason = f'{default_reason} — {end_reason}' if end_reason else default_reason
    employee.status = Employee.Status.TERMINATED
    employee.save(update_fields=['end_date', 'end_reason', 'status'])

    from apps.payroll.services.settlement_payroll import remove_employee_from_draft_payroll_runs

    payroll_cleanup = remove_employee_from_draft_payroll_runs(employee)

    if settlement_type == 'contract_expiry':
        header = '═══ انتهاء عقد بانتهاء مدته ═══'
        statement_title = 'انتهاء عقد بانتهاء مدته'
    elif settlement_type == 'article_74':
        header = '═══ إنهاء العقد بالتراضي (المادة 74) ═══'
        statement_title = f'إنهاء عقد بالتراضي — المادة 74 ({type_label})'
    elif settlement_type == 'article_77':
        header = '═══ إنهاء العقد — سبب غير مشروع (المادة 77) ═══'
        statement_title = f'إنهاء عقد — المادة 77 ({type_label})'
    elif settlement_type == 'article_80':
        header = '═══ إنهاء العقد — سبب مشروع (المادة 80) ═══'
        statement_title = 'إنهاء عقد — المادة 80 (رصيد إجازات فقط)'
    elif settlement_type == 'probation_end':
        header = '═══ إنهاء العقد — نهاية فترة التجربة ═══'
        statement_title = 'إنهاء عقد — نهاية فترة التجربة (رصيد إجازات فقط)'
    else:
        header = '═══ تصفية نهاية خدمة / استقالة ═══'
        statement_title = f'تصفية نهاية خدمة أو استقالة ({type_label})'

    eosb_calc_type = resolve_eosb_settlement_type(settlement_type, article_party)
    content = (
        f'{header}\n'
        f'تاريخ التصفية: {end_date}\n'
        f'نوع التصفية: {type_label}\n'
        f'السبب: {end_reason or "—"}\n'
        f'───────────────────\n'
        f'تاريخ المباشرة: {hire_date}\n'
        f'مدة الخدمة: {service_days} يوم ({service_years} سنة)\n'
    )
    if settlement_type not in LEAVE_ONLY_SETTLEMENTS:
        content += f'آخر راتب إجمالي: {last_salary} ر.س\n'
        content += (
            f'───────────────────\n'
            f'الفئة: {category}\n'
            f'المكافأة الأساسية: {eosb_before} ر.س\n'
        )
        if eosb_calc_type == 'employee' and resignation_note and settlement_type != 'article_74':
            content += f'معامل الاستقالة: {resignation_note}\n'
            content += f'المكافأة بعد المعامل: {eosb} ر.س\n'
        if settlement_type == 'article_77':
            content += (
                f'───────────────────\n'
                f'شرط جزائي (المادة 77): راتب {ARTICLE_77_PENALTY_MONTHS} شهر = {penalty} ر.س\n'
            )
    else:
        content += '───────────────────\n'
        if settlement_type == 'probation_end':
            content += 'مكافأة نهاية الخدمة: 0.00 ر.س (نهاية فترة التجربة)\n'
        else:
            content += 'مكافأة نهاية الخدمة: 0.00 ر.س (المادة 80)\n'
    content += (
        f'───────────────────\n'
        f'{leave_text}\n'
        f'───────────────────\n'
        f'★ إجمالي المستحقات: {total_entitlement} ر.س\n'
    )
    if settlement_type == 'article_77':
        content += f'  (مكافأة {eosb} + إجازة {leave_comp} + جزاء {penalty})\n'
    elif settlement_type in LEAVE_ONLY_SETTLEMENTS:
        content += f'  (إجازة {leave_comp} فقط)\n'
    else:
        content += f'  (مكافأة {eosb} + إجازة {leave_comp})\n'
    if notes:
        content += f'\nملاحظات: {notes}\n'

    EmployeeStatement.objects.create(
        employee=employee,
        statement_type=EmployeeStatement.StatementType.TERMINATE,
        title=statement_title,
        statement_date=end_date,
        content=content,
        created_by=action.requested_by,
    )

    # ── إنشاء سجل في المخصصات (تصفير الرصيد) ──
    from apps.employees.models import EmployeeLedger
    last_ledger = EmployeeLedger.objects.filter(employee=employee).order_by('-date', '-created_at').first()
    prev_leave_days = last_ledger.cumulative_leave_days if last_ledger else Decimal('0')
    prev_leave_amt = last_ledger.cumulative_leave_amount if last_ledger else Decimal('0')
    prev_eosb = last_ledger.cumulative_eosb_amount if last_ledger else Decimal('0')

    EmployeeLedger.objects.create(
        employee=employee,
        transaction_type=EmployeeLedger.TransactionType.FINAL_SETTLEMENT,
        date=end_date,
        leave_days_change=-prev_leave_days,
        leave_amount_change=-prev_leave_amt,
        eosb_amount_change=-prev_eosb,
        cumulative_leave_days=Decimal('0'),
        cumulative_leave_amount=Decimal('0'),
        cumulative_eosb_amount=Decimal('0'),
        notes='تصفية نهائية وتصفير الرصيد',
        created_by=executor
    )

    if settlement_type == 'article_80':
        return (
            f'تم إنهاء عقد {employee.name} بموجب المادة 80 بتاريخ {end_date} — '
            f'رصيد إجازات: {leave_comp} ر.س = إجمالي: {total_entitlement} ر.س'
        )
    if settlement_type == 'probation_end':
        return (
            f'تم إنهاء عقد {employee.name} بنهاية فترة التجربة بتاريخ {end_date} — '
            f'رصيد إجازات: {leave_comp} ر.س = إجمالي: {total_entitlement} ر.س'
        )
    return (
        f'تم تصفية {employee.name} بتاريخ {end_date} — '
        f'مكافأة: {eosb} ر.س + إجازة: {leave_comp} ر.س'
        + (f' + جزاء: {penalty} ر.س' if penalty else '')
        + f' = إجمالي: {total_entitlement} ر.س'
    )

EXECUTORS['end_of_service'] = _execute_end_of_service



def execute_pending_action(action, executor_user):
    """ينفّذ الـ PendingAction المعتمد. يرفع استثناء عند الفشل."""
    if action.executed_at:
        raise ValueError('تم تنفيذ هذا الطلب مسبقاً.')

    fn = EXECUTORS.get(action.action_type)
    if not fn:
        raise ValueError(f'نوع عملية غير معروف: {action.action_type}')

    try:
        msg = fn(action, executor_user)
        action.executed_at = timezone.now()
        action.execution_error = ''
        action.save(update_fields=['executed_at', 'execution_error'])
        try:
            from apps.core.services.whatsapp import notify_whatsapp_action_executed
            notify_whatsapp_action_executed(action, msg)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                'WhatsApp notification failed for pending action %s', action.pk,
            )
        return msg
    except Exception as e:
        action.execution_error = str(e)[:1000]
        action.save(update_fields=['execution_error'])
        raise


# =============================================================================
# دورة الموافقات متعدّدة المراحل (Phase 2)
# =============================================================================

def _notify(*args, **kwargs):
    """import كسول لتجنّب الدوّار."""
    from apps.core.services import notifications as notif
    return notif


def create_pending_action(*, action_type, employee, payload, requested_by, attachment=None):
    """إنشاء طلب معلّق مع لقطة مسار الموافقة."""
    from apps.core.models import PendingAction

    routing = snapshot_routing_fields(employee)
    return PendingAction.objects.create(
        action_type=action_type,
        employee=employee,
        branch=routing['branch'],
        administration=routing['administration'],
        payload=payload,
        attachment=attachment,
        requested_by=requested_by,
    )


@transaction.atomic
def branch_approve(action, user, notes=''):
    """المرحلة الأولى (إدارة/فرع/محاسب) توافق → GM أو تنفيذ فوري لعجز الكاشير."""
    from apps.core.models import PendingAction
    from apps.employees.services.cash_shortage_access import user_can_approve_cash_shortage

    if action.status != PendingAction.Status.PENDING_BRANCH:
        raise ValueError('هذا الطلب ليس في مرحلة الموافقة الأولى.')

    if action.action_type == PendingAction.ActionType.CASH_SHORTAGE:
        if not user_can_approve_cash_shortage(user, action):
            raise ValueError('لا تملك صلاحية اعتماد عجز الكاشير لهذا الفرع.')
        action.status = PendingAction.Status.APPROVED
        action.branch_reviewed_by = user
        action.branch_reviewed_at = timezone.now()
        action.branch_notes = notes or ''
        action.save(update_fields=[
            'status', 'branch_reviewed_by', 'branch_reviewed_at', 'branch_notes',
        ])
        execute_pending_action(action, user)
        notif = _notify()
        if action.requested_by_id:
            notif.notify_user(
                action.requested_by, action,
                title=f'تم تنفيذ طلبك — {action.get_action_type_display()}',
                message=f'الموظف: {action.employee.name}',
                icon='check-circle', color='emerald',
            )
        return action

    action.status = PendingAction.Status.PENDING_GM
    action.branch_reviewed_by = user
    action.branch_reviewed_at = timezone.now()
    action.branch_notes = notes or ''
    action.save(update_fields=[
        'status', 'branch_reviewed_by', 'branch_reviewed_at', 'branch_notes'
    ])

    decision = resolve_first_approver(action)
    approver_label = decision.stage_label
    notif = _notify()
    notif.notify_general_managers(
        action,
        title=f'طلب جديد بانتظار موافقتك — {action.get_action_type_display()}',
        message=f'الموظف: {action.employee.name} • وافق عليه {approver_label}',
        icon='user-cog', color='amber',
    )
    from apps.core.services.whatsapp import workflow_notifier
    workflow_notifier.notify_whatsapp_pending_gm(action)
    return action


@transaction.atomic
def gm_approve_and_assign(action, user, officer, notes=''):
    """المدير العام يوافق ويُسند المهمة لموظف موارد."""
    from apps.core.models import PendingAction, Role

    if action.status != PendingAction.Status.PENDING_GM:
        raise ValueError('هذا الطلب ليس في مرحلة موافقة المدير العام.')
    if not officer or not officer.is_active:
        raise ValueError('يجب اختيار موظف موارد فعّال للإسناد.')
    profile = getattr(officer, 'profile', None)
    if not profile or not profile.role or profile.role.role_type != Role.RoleType.HR_OFFICER:
        raise ValueError('المستخدم المختار ليس "موظف موارد".')

    now = timezone.now()
    action.status = PendingAction.Status.PENDING_OFFICER
    action.gm_reviewed_by = user
    action.gm_reviewed_at = now
    action.gm_notes = notes or ''
    action.assigned_officer = officer
    action.assigned_at = now
    action.save(update_fields=[
        'status', 'gm_reviewed_by', 'gm_reviewed_at', 'gm_notes',
        'assigned_officer', 'assigned_at'
    ])

    notif = _notify()
    notif.notify_user(
        officer, action,
        title=f'مهمة جديدة مُسندة إليك — {action.get_action_type_display()}',
        message=f'الموظف: {action.employee.name} • أسندها {user.get_full_name() or user.username}',
        icon='clipboard-check', color='indigo',
    )
    from apps.core.services.whatsapp import workflow_notifier
    workflow_notifier.notify_whatsapp_officer_assigned(action, officer)
    return action


@transaction.atomic
def officer_approve(action, user, notes=''):
    """موظف الموارد يوافق → يتم التنفيذ تلقائياً."""
    from apps.core.models import PendingAction

    if action.status != PendingAction.Status.PENDING_OFFICER:
        raise ValueError('هذا الطلب ليس في مرحلة موظف الموارد.')
    if action.assigned_officer_id != user.id and not user.is_superuser:
        raise ValueError('هذا الطلب غير مُسند إليك.')

    action.status = PendingAction.Status.APPROVED
    action.officer_reviewed_at = timezone.now()
    action.officer_notes = notes or ''
    action.save(update_fields=[
        'status', 'officer_reviewed_at', 'officer_notes'
    ])

    # التنفيذ الفعلي
    msg = execute_pending_action(action, user)

    # إشعار مقدّم الطلب بالاكتمال
    notif = _notify()
    if action.requested_by_id:
        notif.notify_user(
            action.requested_by, action,
            title=f'تم تنفيذ طلبك — {action.get_action_type_display()}',
            message=f'الموظف: {action.employee.name}',
            icon='check-circle', color='emerald',
        )
    return msg


@transaction.atomic
def return_action(action, user, notes):
    """إرجاع الطلب للأخصائي للتعديل من أي مرحلة."""
    from apps.core.models import PendingAction

    if action.status not in {
        PendingAction.Status.PENDING_BRANCH,
        PendingAction.Status.PENDING_GM,
        PendingAction.Status.PENDING_OFFICER,
    }:
        raise ValueError('لا يمكن إرجاع طلب ليس قيد الموافقة.')
    if not notes or not str(notes).strip():
        raise ValueError('ملاحظات الإرجاع إجبارية.')

    # تحديد المرحلة التي رُجِع منها
    stage_map = {
        PendingAction.Status.PENDING_BRANCH: PendingAction.Stage.BRANCH,
        PendingAction.Status.PENDING_GM: PendingAction.Stage.GM,
        PendingAction.Status.PENDING_OFFICER: PendingAction.Stage.OFFICER,
    }

    action.returned_from_stage = stage_map[action.status]
    action.status = PendingAction.Status.RETURNED
    action.returned_by = user
    action.returned_at = timezone.now()
    action.return_notes = notes
    action.save(update_fields=[
        'status', 'returned_by', 'returned_at',
        'returned_from_stage', 'return_notes'
    ])

    notif = _notify()
    if action.requested_by_id:
        notif.notify_user(
            action.requested_by, action,
            title=f'طلبك مرتجع للتعديل — {action.get_action_type_display()}',
            message=f'السبب: {notes}',
            icon='undo-2', color='amber',
        )
    return action


@transaction.atomic
def resubmit_action(action, user):
    """الأخصائي يعيد إرسال الطلب بعد التعديل → يبدأ من جديد."""
    from apps.core.models import PendingAction

    if action.status != PendingAction.Status.RETURNED:
        raise ValueError('لا يمكن إعادة إرسال طلب غير مُرتجَع.')
    if action.requested_by_id != user.id and not user.is_superuser:
        raise ValueError('فقط مقدّم الطلب يمكنه إعادة إرساله.')

    action.status = PendingAction.Status.PENDING_BRANCH
    action.resubmit_count = (action.resubmit_count or 0) + 1
    # نُبقي بيانات الإرجاع للسجل التاريخي ولكن نمسح "صناديق" المراحل القديمة
    action.branch_reviewed_by = None
    action.branch_reviewed_at = None
    action.branch_notes = ''
    action.gm_reviewed_by = None
    action.gm_reviewed_at = None
    action.gm_notes = ''
    action.assigned_officer = None
    action.assigned_at = None
    action.officer_reviewed_at = None
    action.officer_notes = ''
    action.save(update_fields=[
        'status', 'resubmit_count',
        'branch_reviewed_by', 'branch_reviewed_at', 'branch_notes',
        'gm_reviewed_by', 'gm_reviewed_at', 'gm_notes',
        'assigned_officer', 'assigned_at',
        'officer_reviewed_at', 'officer_notes',
    ])

    notify_on_first_stage(
        action,
        title=f'طلب مُعاد بعد التعديل — {action.get_action_type_display()}',
        message=f'الموظف: {action.employee.name} • محاولة #{action.resubmit_count}',
        icon='refresh-cw',
        color='primary',
    )
    return action


def notify_branch_on_create(action):
    """يُستدعى مرة واحدة بعد إنشاء PendingAction جديد."""
    from apps.core.services.whatsapp import workflow_notifier

    workflow_notifier.notify_whatsapp_request_created(action)
    notify_on_first_stage(
        action,
        title=f'طلب جديد بانتظار موافقتك — {action.get_action_type_display()}',
        message=f'الموظف: {action.employee.name}'
                f' • مقدّم الطلب: {action.requested_by.get_full_name() or action.requested_by.username}',
        icon='inbox',
        color='primary',
    )
