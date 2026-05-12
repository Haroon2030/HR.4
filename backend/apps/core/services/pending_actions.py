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
    'custody_receive': None,  # ملحقة أدناه بعد التعريف
    'custody_clear': None,
    'job_offer': None,
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
def _execute_job_offer(action, executor):
    from apps.employees.models import EmployeeJobOffer
    p = action.payload
    employee = action.employee
    serial = p.get('serial_number') or _build_form_serial_local('EL', employee.id)
    offer = EmployeeJobOffer.objects.create(
        employee=employee,
        serial_number=serial,
        addressed_to=p['addressed_to'],
        purpose=p.get('purpose', ''),
        issued_at=_to_date(p['issued_at']),
        notes=p.get('notes', ''),
        document=action.attachment or None,
        created_by=action.requested_by,
    )
    return f'تم إصدار عرض وظيفي إلى {offer.addressed_to} للموظف {employee.name}'


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


EXECUTORS['custody_receive'] = _execute_custody_receive
EXECUTORS['custody_clear'] = _execute_custody_clear
EXECUTORS['job_offer'] = _execute_job_offer
EXECUTORS['business_trip'] = _execute_business_trip


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


# =============================================================================
# دورة الموافقات متعدّدة المراحل (Phase 2)
# =============================================================================

def _notify(*args, **kwargs):
    """import كسول لتجنّب الدوّار."""
    from apps.core.services import notifications as notif
    return notif


@transaction.atomic
def branch_approve(action, user, notes=''):
    """مدير الفرع يوافق → ينتقل الطلب إلى المدير العام."""
    from apps.core.models import PendingAction
    if action.status != PendingAction.Status.PENDING_BRANCH:
        raise ValueError('هذا الطلب ليس في مرحلة موافقة مدير الفرع.')

    action.status = PendingAction.Status.PENDING_GM
    action.branch_reviewed_by = user
    action.branch_reviewed_at = timezone.now()
    action.branch_notes = notes or ''
    action.save(update_fields=[
        'status', 'branch_reviewed_by', 'branch_reviewed_at', 'branch_notes'
    ])

    notif = _notify()
    notif.notify_general_managers(
        action,
        title=f'طلب جديد بانتظار موافقتك — {action.get_action_type_display()}',
        message=f'الموظف: {action.employee.name} • وافق عليه مدير الفرع',
        icon='user-cog', color='amber',
    )
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

    # إشعار مدير الفرع بإعادة الإرسال
    notif = _notify()
    notif.notify_branch_managers(
        action,
        title=f'طلب مُعاد بعد التعديل — {action.get_action_type_display()}',
        message=f'الموظف: {action.employee.name} • محاولة #{action.resubmit_count + 1}',
        icon='refresh-cw', color='primary',
    )
    return action


def notify_branch_on_create(action):
    """يُستدعى مرة واحدة بعد إنشاء PendingAction جديد."""
    notif = _notify()
    notif.notify_branch_managers(
        action,
        title=f'طلب جديد بانتظار موافقتك — {action.get_action_type_display()}',
        message=f'الموظف: {action.employee.name}'
                f' • مقدّم الطلب: {action.requested_by.get_full_name() or action.requested_by.username}',
        icon='inbox', color='primary',
    )
