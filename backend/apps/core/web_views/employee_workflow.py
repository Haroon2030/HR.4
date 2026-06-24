"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
import json
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages



# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.web_views._helpers import (
    employee_branch_access_required,
)
from apps.core.decorators import any_permission_required, permission_required
from apps.core.salary_access import salary_view_required
from apps.core.services.pending_actions import create_and_execute_settlement_action, create_pending_action

@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def add_employee_leave(request, employee_id):
    """تقديم إجازة للموظف مع التحقق من الكفالة والرصيد المتاح."""
    from decimal import Decimal
    from apps.employees.models import Employee, EmployeeLeave
    from apps.core.forms import LeaveRequestForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن تقديم إجازة لموظف منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    # تحقّق: يجب أن يكون الموظف على كفالة
    if not employee.sponsorship_id:
        messages.error(request, 'لا يمكن تقديم إجازة: الموظف غير مُسجَّل على كفالة.')
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = LeaveRequestForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    leave_type = cd['leave_type']
    d_from = cd['date_from']
    d_to = cd['date_to']
    days = Decimal((d_to - d_from).days + 1)

    # تحقّق: لا تتجاوز الرصيد المتاح (للإجازة السنوية فقط)
    if leave_type == EmployeeLeave.LeaveType.ANNUAL:
        remaining = Decimal(employee.remaining_leave_days or 0)
        if days > remaining:
            messages.error(
                request,
                f'الرصيد غير كافٍ: الرصيد المتاح {remaining} يوم، والمطلوب {days} يوم.'
            )
            return redirect('web:view_employee', employee_id=employee.id)

    create_pending_action(
        action_type='leave',
        employee=employee,
        payload={
            'leave_type': leave_type,
            'date_from': d_from.isoformat(),
            'date_to': d_to.isoformat(),
            'days': str(days),
            'notes': cd.get('notes', ''),
        },
        requested_by=request.user,
        attachment=files.get('document'),
    )

    messages.success(
        request,
        f'تم إرسال طلب الإجازة ({days} يوم) لمسار الموافقات.',
    )
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@any_permission_required(
    'employees.edit_leave', 'employees.edit',
)
@employee_branch_access_required
def edit_employee_leave(request, employee_id, leave_id):
    """تعديل إجازة مُسجَّلة من تبويب الإجازات."""
    from decimal import Decimal
    from apps.employees.models import Employee, EmployeeLeave
    from apps.core.forms import LeaveRequestForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename
    from apps.employees.services.employee_record_locks import leave_is_editable

    employee = get_object_or_404(Employee, id=employee_id)
    leave = get_object_or_404(EmployeeLeave, id=leave_id, employee_id=employee.id)

    if not leave_is_editable(leave):
        messages.error(request, 'لا يمكن تعديل إجازة مُطبّقة على مسير رواتب مُرحّل.')
        return _redirect_employee_tab(employee.id, 'leaves')

    if request.method != 'POST':
        return _redirect_employee_tab(employee.id, 'leaves')

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = LeaveRequestForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return _redirect_employee_tab(employee.id, 'leaves')

    cd = form.cleaned_data
    leave_type = cd['leave_type']
    d_from = cd['date_from']
    d_to = cd['date_to']
    days = Decimal((d_to - d_from).days + 1)

    if leave_type == EmployeeLeave.LeaveType.ANNUAL:
        remaining = Decimal(employee.remaining_leave_days or 0)
        if leave.leave_type == EmployeeLeave.LeaveType.ANNUAL:
            remaining += Decimal(leave.days or 0)
        if days > remaining:
            messages.error(
                request,
                f'الرصيد غير كافٍ: الرصيد المتاح {remaining} يوم، والمطلوب {days} يوم.',
            )
            return _redirect_employee_tab(employee.id, 'leaves')

    leave.leave_type = leave_type
    leave.date_from = d_from
    leave.date_to = d_to
    leave.days = days
    leave.notes = cd.get('notes', '') or ''
    if files.get('document'):
        leave.document = files['document']
    leave.save()
    messages.success(request, 'تم تحديث سجل الإجازة.')
    return _redirect_employee_tab(employee.id, 'leaves')


@login_required
@any_permission_required(
    'employees.delete_leave', 'employees.delete',
    'employees.edit_leave', 'employees.edit',
)
@employee_branch_access_required
def delete_employee_leave(request, employee_id, leave_id):
    """حذف إجازة مُسجَّلة من تبويب الإجازات."""
    from apps.employees.models import Employee, EmployeeLeave
    from apps.employees.services.employee_record_locks import leave_is_editable

    employee = get_object_or_404(Employee, id=employee_id)
    leave = get_object_or_404(EmployeeLeave, id=leave_id, employee_id=employee.id)

    if request.method != 'POST':
        return _redirect_employee_tab(employee.id, 'leaves')

    if not leave_is_editable(leave):
        messages.error(request, 'لا يمكن حذف إجازة مُطبّقة على مسير رواتب مُرحّل.')
        return _redirect_employee_tab(employee.id, 'leaves')

    leave.delete()
    messages.success(request, 'تم حذف سجل الإجازة.')
    return _redirect_employee_tab(employee.id, 'leaves')


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def terminate_employee(request, employee_id):
    """تقديم طلب تصفية (ينتظر موافقة مدير الفرع)."""
    from apps.employees.models import Employee
    from apps.core.forms import TerminateEmployeeForm

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'الموظف منتهي الخدمة بالفعل.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    form = TerminateEmployeeForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    try:
        _, msg = create_and_execute_settlement_action(
            action_type='terminate',
            employee=employee,
            payload={
                'end_date': cd['end_date'].isoformat(),
                'end_reason': cd.get('end_reason', ''),
            },
            requested_by=request.user,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('web:view_employee', employee_id=employee.id)
    messages.success(request, msg or 'تمت تصفية الموظف مباشرة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def reactivate_employee(request, employee_id):
    """تقديم طلب إعادة تفعيل موظف مُصفّى (ينتظر موافقة مدير الفرع)."""
    from apps.employees.models import Employee
    from apps.core.forms import ReactivateEmployeeForm

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    if employee.status != Employee.Status.TERMINATED:
        messages.error(request, 'الموظف ليس في حالة منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)

    form = ReactivateEmployeeForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    create_pending_action(
        action_type='reactivate',
        employee=employee,
        payload={
            'new_hire_date': cd['new_hire_date'].isoformat(),
            'reactivation_reason': cd['reactivation_reason'],
            'new_status': cd['new_status'],
        },
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب إعادة التفعيل إلى مدير الإدارة/الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@any_permission_required('employees.edit_salary', 'payroll.manage', 'payroll.process')
@employee_branch_access_required
def adjust_employee_salary(request, employee_id):
    """تقديم طلب تعديل راتب (ينتظر موافقة مدير الفرع)."""
    from decimal import Decimal, InvalidOperation

    from apps.employees.models import Employee
    from apps.core.forms import SalaryAdjustForm

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن تعديل راتب موظف منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    post = request.POST.copy()
    if not (post.get('new_basic_salary') or '').strip():
        try:
            raise_amt = Decimal(post.get('raise_amount', '0'))
            new_basic = (employee.basic_salary or Decimal('0')) + raise_amt
            post['new_basic_salary'] = str(new_basic.quantize(Decimal('0.01')))
        except (InvalidOperation, TypeError, ValueError):
            pass

    form = SalaryAdjustForm(post)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    create_pending_action(
        action_type='salary_adjust',
        employee=employee,
        payload={
            'new_basic_salary': str(cd['new_basic_salary']),
            'effective_date': cd['effective_date'].isoformat(),
            'reason': cd['reason'],
        },
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب تعديل الراتب إلى مدير الإدارة/الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def transfer_employee(request, employee_id):
    """تقديم طلب نقل (ينتظر موافقة مدير الفرع)."""
    from apps.employees.models import Employee
    from apps.core.forms import TransferEmployeeForm

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن نقل موظف منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    form = TransferEmployeeForm(request.POST, user=request.user)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    new_branch = cd.get('new_branch')
    new_dept = cd.get('new_department')

    create_pending_action(
        action_type='transfer',
        employee=employee,
        payload={
            'transfer_date': cd['transfer_date'].isoformat(),
            'reason': cd['reason'],
            'new_branch_id': new_branch.id if new_branch else None,
            'new_department_id': new_dept.id if new_dept else None,
        },
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب النقل إلى مدير إدارة العمليات للموافقة الأولى.')
    return redirect('web:view_employee', employee_id=employee.id)


# =============================================================================
# Work Schedule (شهر-أيام مظللة)
# =============================================================================


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def set_work_schedule(request, employee_id):
    """حفظ جداول الدوام كصناديق شهرية بأيام مُظلَّلة.

    يستقبل حقل JSON `boxes_json` يحوي قائمة صناديق:
    [{"id":"b1","year":2026,"month":4,"days":[1,5,12]}, ...]
    """
    from apps.employees.models import Employee
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    raw = request.POST.get('boxes_json') or '[]'
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        data = []

    cleaned = []
    if isinstance(data, list):
        for idx, box in enumerate(data):
            if not isinstance(box, dict):
                continue
            try:
                year = int(box.get('year'))
                month = int(box.get('month'))
            except (TypeError, ValueError):
                continue
            if not (1900 <= year <= 2100 and 1 <= month <= 12):
                continue
            raw_days = box.get('days') or []
            days = []
            if isinstance(raw_days, list):
                for d in raw_days:
                    try:
                        di = int(d)
                    except (TypeError, ValueError):
                        continue
                    if 1 <= di <= 31 and di not in days:
                        days.append(di)

            day_codes: dict[str, str] = {}
            raw_codes = box.get('day_codes') or {}
            if isinstance(raw_codes, dict):
                allowed = {'d', 'off', 'check', 'v'}
                for k, v in raw_codes.items():
                    try:
                        di = int(k)
                    except (TypeError, ValueError):
                        continue
                    if not (1 <= di <= 31):
                        continue
                    code = str(v or '').strip()
                    if not code:
                        continue
                    norm = code.lower()
                    if norm in ('d', 'check', 'v') or code == '✓':
                        day_codes[str(di)] = '✓'
                        if di not in days:
                            days.append(di)
                    elif norm in allowed:
                        day_codes[str(di)] = norm

            days.sort()

            shift_label = str(box.get('shift_label') or '').strip()[:200]
            if not shift_label:
                legacy_shift_labels = {
                    1: 'الوردية 1 (8ص–4م)',
                    2: 'الوردية 2 (4م–12ص)',
                    3: 'الوردية 3 (12ص–8ص)',
                }
                try:
                    shift_num = int(box.get('shift') or 0)
                    shift_label = legacy_shift_labels.get(shift_num, '')
                except (TypeError, ValueError):
                    shift_label = ''

            notes = str(box.get('notes') or '').strip()[:2000]

            cleaned.append({
                'id': str(box.get('id') or f'b{idx+1}'),
                'year': year,
                'month': month,
                'days': days,
                'day_codes': day_codes,
                'shift_label': shift_label,
                'notes': notes,
            })

    payload = {'version': 3, 'boxes': cleaned}

    # وضع الإلحاق: ندمج الجداول الجديدة مع المحفوظة سابقاً
    mode = (request.POST.get('mode') or '').strip()
    existing_boxes = []
    try:
        _old = json.loads(employee.work_schedule or '') if employee.work_schedule else None
        if isinstance(_old, dict) and isinstance(_old.get('boxes'), list):
            existing_boxes = _old['boxes']
    except (ValueError, TypeError):
        existing_boxes = []

    if mode == 'append':
        payload = {'version': 3, 'boxes': existing_boxes + cleaned}
    else:
        # حماية من المسح غير المقصود: ارفض الحفظ إذا كانت القائمة الجديدة
        # ستقلّص عدد الأشهر دون إقرار صريح من المستخدم.
        confirm_clear = (request.POST.get('confirm_clear') or '').strip() in ('1', 'true', 'yes')
        if len(existing_boxes) > 0 and len(cleaned) < len(existing_boxes) and not confirm_clear:
            messages.error(
                request,
                f'تم رفض الحفظ: عدد الأشهر الجديد ({len(cleaned)}) أقل من المحفوظ ({len(existing_boxes)}). '
                f'إذا كنت تريد فعلاً تقليلها، أكّد العملية وأعد المحاولة.'
            )
            return redirect('web:view_employee', employee_id=employee.id)

    employee.work_schedule = json.dumps(payload, ensure_ascii=False)
    employee.save(update_fields=['work_schedule'])

    # ── إرسال بالبريد إن طُلب ──
    send_email_flag = bool(request.POST.get('send_email'))
    if send_email_flag:
        from apps.core.services.email_recipients import resolve_statement_email_recipients

        recipients = resolve_statement_email_recipients(
            employee,
            posted_employee_email=request.POST.get('employee_email') or '',
            posted_hr_email=request.POST.get('hr_email') or '',
            actor=request.user,
        )
        if not recipients:
            messages.warning(request, f'تم حفظ {len(cleaned)} شهر — لكن لم يتم الإرسال (لا يوجد بريد).')
            return redirect('web:view_employee', employee_id=employee.id)
        try:
            from apps.core.services.email_delivery import SmtpConnectionError, SmtpNotConfiguredError
            from apps.core.services.work_schedule_mail import send_work_schedule_email

            email_boxes = payload.get('boxes') if isinstance(payload.get('boxes'), list) else cleaned
            send_work_schedule_email(
                employee=employee,
                boxes_data=email_boxes,
                recipients=recipients,
            )
            messages.success(request, f'تم حفظ الجدول وإرساله رسمياً (PDF) إلى: {", ".join(recipients)}')
        except (SmtpNotConfiguredError, SmtpConnectionError) as e:
            messages.error(request, f'تم حفظ الجدول لكن فشل الإرسال: {e}')
        except Exception as e:
            messages.error(request, f'تم حفظ الجدول لكن فشل الإرسال: {e}')
    else:
        schedule_action = (request.POST.get('schedule_action') or 'save').strip()
        deleted_label = (request.POST.get('deleted_month_label') or '').strip()
        if schedule_action == 'delete':
            if deleted_label:
                messages.success(request, f'تم حذف جدول دوام {deleted_label}')
            else:
                messages.success(request, 'تم حذف الشهر من جدول الدوام')
        else:
            count = len(cleaned)
            if count == 1:
                messages.success(request, 'تم حفظ شهر واحد')
            else:
                messages.success(request, f'تم حفظ {count} شهر')
    return redirect('web:view_employee', employee_id=employee.id)


# =============================================================================
# Custody / Job Offer / Business Trip — تذهب لدورة الموافقات (PendingAction)
# =============================================================================

@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def receive_employee_custody(request, employee_id):
    """طلب استلام عهدة جديدة (ينتظر دورة الموافقات)."""
    from apps.employees.models import Employee
    from apps.core.forms import CustodyReceiveForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن تسجيل عهدة لموظف منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = CustodyReceiveForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    create_pending_action(
        action_type='custody_receive',
        employee=employee,
        payload={
            'item_name': cd['item_name'],
            'item_details': cd.get('item_details', ''),
            'quantity': int(cd.get('quantity') or 1),
            'estimated_value': str(cd['estimated_value']) if cd.get('estimated_value') is not None else None,
            'received_at': cd['received_at'].isoformat(),
            'notes': cd.get('notes', ''),
        },
        attachment=files.get('document') or None,
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب استلام العهدة إلى مدير الإدارة/الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def clear_employee_custody(request, employee_id):
    """طلب تصفية عهدة موجودة (ينتظر دورة الموافقات)."""
    from apps.employees.models import Employee, EmployeeCustody
    from apps.core.forms import CustodyClearForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = CustodyClearForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    custody = EmployeeCustody.objects.filter(
        id=cd['custody_id'], employee=employee, status=EmployeeCustody.Status.ACTIVE
    ).first()
    if not custody:
        messages.error(request, 'العهدة غير موجودة أو سبق تصفيتها.')
        return redirect('web:view_employee', employee_id=employee.id)

    create_pending_action(
        action_type='custody_clear',
        employee=employee,
        payload={
            'custody_id': custody.id,
            'item_name': custody.item_name,
            'returned_at': cd['returned_at'].isoformat(),
            'return_notes': cd.get('return_notes', ''),
        },
        attachment=files.get('document') or None,
        requested_by=request.user,
    )
    messages.success(request, f'تم إرسال طلب تصفية العهدة "{custody.item_name}" إلى مدير الإدارة/الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def add_employee_business_trip(request, employee_id):
    """طلب رحلة عمل (ينتظر دورة الموافقات)."""
    from apps.employees.models import Employee
    from apps.core.forms import BusinessTripForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن تسجيل رحلة عمل لموظف منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = BusinessTripForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    create_pending_action(
        action_type='business_trip',
        employee=employee,
        payload={
            'destination': cd['destination'],
            'purpose': cd['purpose'],
            'start_date': cd['start_date'].isoformat(),
            'end_date': cd['end_date'].isoformat(),
            'estimated_cost': str(cd['estimated_cost']) if cd.get('estimated_cost') is not None else None,
            'notes': cd.get('notes', ''),
        },
        attachment=files.get('document') or None,
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب رحلة العمل إلى مدير الإدارة/الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def add_employee_loan(request, employee_id):
    """تقديم سلفة موظف (ينتظر دورة الموافقات)."""
    from apps.employees.models import Employee
    from apps.core.forms import LoanRequestForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن تقديم سلفة لموظف منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = LoanRequestForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    create_pending_action(
        action_type='loan_request',
        employee=employee,
        payload={
            'amount': str(cd['amount']),
            'monthly_deduction': str(cd['monthly_deduction']),
            'installments': int(cd.get('installments') or 1),
            'reason': cd.get('reason', ''),
            'issued_at': cd['issued_at'].isoformat(),
            'first_deduction_date': cd['first_deduction_date'].isoformat() if cd.get('first_deduction_date') else None,
            'notes': cd.get('notes', ''),
        },
        attachment=files.get('document') or None,
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب السلفة إلى مدير الإدارة/الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def add_employee_absence(request, employee_id):
    """تسجيل غياب موظف (ينتظر دورة الموافقات، يُخصم من الراتب عند التنفيذ)."""
    from apps.employees.models import Employee
    from apps.core.forms import AbsenceForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن تسجيل غياب لموظف منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = AbsenceForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    create_pending_action(
        action_type='absence',
        employee=employee,
        payload={
            'absence_date': cd['absence_date'].isoformat(),
            'days': int(cd['days']),
            'reason': cd.get('reason', ''),
            'notes': cd.get('notes', ''),
        },
        attachment=files.get('document') or None,
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب تسجيل الغياب إلى مدير الإدارة/الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


def _redirect_employee_absences_tab(employee_id: int):
    from django.urls import reverse
    return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee_id})}?tab=absences#employee-tab-panel')


def _redirect_employee_tab(employee_id: int, tab: str):
    from django.urls import reverse
    return redirect(f'{reverse("web:view_employee", kwargs={"employee_id": employee_id})}?tab={tab}#employee-tab-panel')


@login_required
@any_permission_required('employees.edit_loan', 'employees.edit')
@employee_branch_access_required
def edit_employee_loan(request, employee_id, loan_id):
    """تعديل سلفة موظف."""
    from django.db import transaction
    from apps.employees.models import Employee, EmployeeLoan, LoanInstallment
    from apps.core.forms import LoanRequestForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename
    from apps.employees.services.employee_record_locks import loan_has_consumed_installments

    employee = get_object_or_404(Employee, id=employee_id)
    loan = get_object_or_404(EmployeeLoan, id=loan_id, employee_id=employee.id)

    if request.method != 'POST':
        return _redirect_employee_tab(employee.id, 'loans')

    locked = loan_has_consumed_installments(loan)
    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    if locked:
        loan.reason = (request.POST.get('reason') or '').strip()
        loan.notes = (request.POST.get('notes') or '').strip()
        if files.get('document'):
            loan.document = files['document']
        loan.save()
        messages.success(request, 'تم تحديث بيانات السلفة (السبب/الملاحظات فقط — يوجد أقساط مُحصّلة).')
        return _redirect_employee_tab(employee.id, 'loans')

    form = LoanRequestForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return _redirect_employee_tab(employee.id, 'loans')

    cd = form.cleaned_data
    with transaction.atomic():
        loan.amount = cd['amount']
        loan.monthly_deduction = cd['monthly_deduction']
        loan.installments = int(cd.get('installments') or 1)
        loan.reason = cd.get('reason', '') or ''
        loan.notes = cd.get('notes', '') or ''
        loan.issued_at = cd['issued_at']
        loan.first_deduction_date = cd.get('first_deduction_date')
        if files.get('document'):
            loan.document = files['document']
        loan.save()
        loan.installments_log.all().delete()
        loan.generate_installments()

    messages.success(request, 'تم تحديث السلفة وإعادة توليد الأقساط.')
    return _redirect_employee_tab(employee.id, 'loans')


@login_required
@any_permission_required(
    'employees.delete_loan', 'employees.delete',
    'employees.edit_loan', 'employees.edit',
)
@employee_branch_access_required
def delete_employee_loan(request, employee_id, loan_id):
    """حذف سلفة موظف."""
    from apps.employees.models import Employee, EmployeeLoan
    from apps.employees.services.employee_record_locks import loan_has_consumed_installments

    employee = get_object_or_404(Employee, id=employee_id)
    loan = get_object_or_404(EmployeeLoan, id=loan_id, employee_id=employee.id)

    if request.method != 'POST':
        return _redirect_employee_tab(employee.id, 'loans')

    if loan_has_consumed_installments(loan):
        messages.error(request, 'لا يمكن حذف سلفة بها أقساط مُحصّلة أو مُطبّقة على مسير رواتب.')
        return _redirect_employee_tab(employee.id, 'loans')

    loan.delete()
    messages.success(request, 'تم حذف السلفة.')
    return _redirect_employee_tab(employee.id, 'loans')


@login_required
@any_permission_required('employees.edit_ledger', 'employees.edit')
@employee_branch_access_required
def edit_employee_ledger(request, employee_id, ledger_id):
    """تعديل ملاحظات سجل مخصصات."""
    from apps.employees.models import Employee, EmployeeLedger
    from apps.employees.services.employee_record_locks import ledger_entry_is_locked

    employee = get_object_or_404(Employee, id=employee_id)
    entry = get_object_or_404(EmployeeLedger, id=ledger_id, employee_id=employee.id)

    if request.method != 'POST':
        return _redirect_employee_tab(employee.id, 'accruals')

    if ledger_entry_is_locked(entry):
        messages.error(request, 'لا يمكن تعديل سجل مرتبط بمسير رواتب أو تصفية نهائية.')
        return _redirect_employee_tab(employee.id, 'accruals')

    entry.notes = (request.POST.get('notes') or '').strip()
    entry.save(update_fields=['notes', 'updated_at'])
    messages.success(request, 'تم تحديث ملاحظات السجل.')
    return _redirect_employee_tab(employee.id, 'accruals')


@login_required
@any_permission_required(
    'employees.delete_ledger', 'employees.delete',
    'employees.edit_ledger', 'employees.edit',
)
@employee_branch_access_required
def delete_employee_ledger(request, employee_id, ledger_id):
    """حذف سجل مخصصات مع إعادة احتساب التراكمي."""
    from django.db import transaction
    from apps.employees.models import Employee, EmployeeLedger
    from apps.employees.services.employee_record_locks import ledger_entry_is_locked
    from apps.employees.services.ledger_recalculate import recalculate_employee_ledger

    employee = get_object_or_404(Employee, id=employee_id)
    entry = get_object_or_404(EmployeeLedger, id=ledger_id, employee_id=employee.id)

    if request.method != 'POST':
        return _redirect_employee_tab(employee.id, 'accruals')

    if ledger_entry_is_locked(entry):
        messages.error(request, 'لا يمكن حذف سجل مرتبط بمسير رواتب أو تصفية نهائية.')
        return _redirect_employee_tab(employee.id, 'accruals')

    with transaction.atomic():
        entry.delete()
        recalculate_employee_ledger(employee)

    messages.success(request, 'تم حذف السجل وإعادة احتساب الأرصدة.')
    return _redirect_employee_tab(employee.id, 'accruals')


@login_required
@any_permission_required('employees.edit_absence', 'employees.edit')
@employee_branch_access_required
def edit_employee_absence(request, employee_id, absence_id):
    """تعديل سجل غياب (مدير الموارد / الأدمن)."""
    from apps.employees.models import Employee, EmployeeAbsence
    from apps.core.forms import AbsenceForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    absence = get_object_or_404(EmployeeAbsence, id=absence_id, employee_id=employee.id)

    if absence.applied_to_payroll_id:
        messages.error(request, 'لا يمكن تعديل غياب مُطبّق على مسير رواتب مُرحّل.')
        return _redirect_employee_absences_tab(employee.id)

    if request.method != 'POST':
        return _redirect_employee_absences_tab(employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = AbsenceForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return _redirect_employee_absences_tab(employee.id)

    cd = form.cleaned_data
    absence.absence_date = cd['absence_date']
    absence.days = int(cd['days'])
    absence.reason = cd.get('reason', '') or ''
    absence.notes = cd.get('notes', '') or ''
    if files.get('document'):
        absence.document = files['document']
    absence.save()
    messages.success(request, 'تم تحديث سجل الغياب.')
    return _redirect_employee_absences_tab(employee.id)


@login_required
@any_permission_required(
    'employees.delete_absence', 'employees.delete',
    'employees.edit_absence', 'employees.edit',
)
@employee_branch_access_required
def delete_employee_absence(request, employee_id, absence_id):
    """حذف سجل غياب (مدير الموارد / الأدمن)."""
    from apps.employees.models import Employee, EmployeeAbsence

    employee = get_object_or_404(Employee, id=employee_id)
    absence = get_object_or_404(EmployeeAbsence, id=absence_id, employee_id=employee.id)

    if request.method != 'POST':
        return _redirect_employee_absences_tab(employee.id)

    if absence.applied_to_payroll_id:
        messages.error(request, 'لا يمكن حذف غياب مُطبّق على مسير رواتب مُرحّل.')
        return _redirect_employee_absences_tab(employee.id)

    absence.delete()
    messages.success(request, 'تم حذف سجل الغياب.')
    return _redirect_employee_absences_tab(employee.id)


@login_required
@permission_required('cash_shortages.add')
@employee_branch_access_required
def add_employee_cash_shortage(request, employee_id):
    """تسجيل عجز كاشير لموظف (ينتظر اعتماد محاسب الفرع)."""
    from apps.employees.models import Employee
    from apps.core.forms import CashShortageForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن تسجيل عجز لموظف منتهي الخدمة.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = CashShortageForm(request.POST, files, user=request.user, employee=employee)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    create_pending_action(
        action_type='cash_shortage',
        employee=employee,
        payload={
            'shortage_date': cd['shortage_date'].isoformat(),
            'amount': str(cd['amount']),
            'branch_id': cd['branch'].id,
            'notes': cd.get('notes', ''),
        },
        attachment=cd['document'],
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب عجز الكاشير إلى محاسب الفرع للاعتماد.')
    return redirect('web:view_employee', employee_id=employee.id)


# =============================================================================
# Roles Management
# =============================================================================


# =============================================================================
# تصفية نهاية خدمة أو استقالة
# =============================================================================

@login_required
@permission_required('employee_tab_termination.execute')
@salary_view_required
@employee_branch_access_required
def end_of_service_employee(request, employee_id):
    """تقديم طلب تصفية نهاية خدمة أو استقالة مع حساب المكافأة وفقاً لـ EOSB."""
    from apps.employees.models import Employee
    from apps.core.forms import EndOfServiceForm

    employee = get_object_or_404(Employee, id=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'الموظف منتهي الخدمة بالفعل.')
        return redirect('web:view_employee', employee_id=employee.id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    form = EndOfServiceForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    try:
        _, msg = create_and_execute_settlement_action(
            action_type='end_of_service',
            employee=employee,
            payload={
                'end_date': cd['end_date'].isoformat(),
                'terminated_by': cd['terminated_by'],
                'article_party': cd.get('article_party') or cd.get('article_77_party', ''),
                'end_reason': cd.get('end_reason', ''),
                'notes': cd.get('notes', ''),
            },
            requested_by=request.user,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('web:view_employee', employee_id=employee.id)
    messages.success(request, msg or 'تمت تصفية نهاية الخدمة مباشرة.')
    return redirect('web:view_employee', employee_id=employee.id)
