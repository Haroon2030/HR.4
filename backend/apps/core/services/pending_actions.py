"""
خدمة تنفيذ العمليات السريعة المعلّقة بعد موافقة مدير الفرع.

كل دالة executor تتلقى (PendingAction, executor_user) وتُطبّق العملية فعلياً
على الموظف وتُسجّل ما يلزم في EmployeeStatement.
"""
import json
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone


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

    d_from = _to_date(p['date_from'])
    d_to = _to_date(p['date_to'])
    days = _to_decimal(p['days'])
    leave_type = p.get('leave_type', EmployeeLeave.LeaveType.ANNUAL)

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
    return f'تمت تصفية {employee.name} بتاريخ {end_date}'


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
}


def execute_pending_action(action, executor_user):
    """ينفّذ الـ PendingAction المعتمد. يرفع استثناء عند الفشل."""
    fn = EXECUTORS.get(action.action_type)
    if not fn:
        raise ValueError(f'نوع عملية غير معروف: {action.action_type}')

    try:
        msg = fn(action, executor_user)
        action.executed_at = timezone.now()
        action.execution_error = ''
        action.save(update_fields=['executed_at', 'execution_error'])
        return msg
    except Exception as e:
        action.execution_error = str(e)[:1000]
        action.save(update_fields=['execution_error'])
        raise
