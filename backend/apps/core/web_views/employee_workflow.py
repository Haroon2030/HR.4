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
from apps.core.decorators import permission_required

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

    EmployeeLeave.objects.create(
        employee=employee,
        leave_type=leave_type,
        date_from=d_from,
        date_to=d_to,
        days=days,
        notes=cd.get('notes', ''),
        document=files.get('document'),
        created_by=request.user,
    )

    # خصم الإجازة السنوية من الرصيد
    if leave_type == EmployeeLeave.LeaveType.ANNUAL:
        employee.available_leave_balance = (
            Decimal(employee.available_leave_balance or 0) + days
        )
        employee.save(update_fields=['available_leave_balance'])

    messages.success(request, f'تم تسجيل الإجازة ({days} يوم) بنجاح.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def terminate_employee(request, employee_id):
    """تقديم طلب تصفية (ينتظر موافقة مدير الفرع)."""
    from apps.employees.models import Employee
    from apps.core.models import PendingAction
    from apps.core.forms import TerminateEmployeeForm

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    form = TerminateEmployeeForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    PendingAction.objects.create(
        action_type=PendingAction.ActionType.TERMINATE,
        employee=employee,
        branch=employee.branch,
        payload={
            'end_date': cd['end_date'].isoformat(),
            'end_reason': cd.get('end_reason', ''),
        },
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب تصفية الموظف إلى مدير الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def reactivate_employee(request, employee_id):
    """تقديم طلب إعادة تفعيل موظف مُصفّى (ينتظر موافقة مدير الفرع)."""
    from apps.employees.models import Employee
    from apps.core.models import PendingAction
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
    PendingAction.objects.create(
        action_type=PendingAction.ActionType.REACTIVATE,
        employee=employee,
        branch=employee.branch,
        payload={
            'new_hire_date': cd['new_hire_date'].isoformat(),
            'reactivation_reason': cd['reactivation_reason'],
            'new_status': cd['new_status'],
        },
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب إعادة التفعيل إلى مدير الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def adjust_employee_salary(request, employee_id):
    """تقديم طلب تعديل راتب (ينتظر موافقة مدير الفرع)."""
    from apps.employees.models import Employee
    from apps.core.models import PendingAction
    from apps.core.forms import SalaryAdjustForm

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    form = SalaryAdjustForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    PendingAction.objects.create(
        action_type=PendingAction.ActionType.SALARY_ADJUST,
        employee=employee,
        branch=employee.branch,
        payload={
            'new_basic_salary': str(cd['new_basic_salary']),
            'effective_date': cd['effective_date'].isoformat(),
            'reason': cd['reason'],
        },
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب تعديل الراتب إلى مدير الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def transfer_employee(request, employee_id):
    """تقديم طلب نقل (ينتظر موافقة مدير الفرع)."""
    from apps.employees.models import Employee
    from apps.core.models import PendingAction
    from apps.core.forms import TransferEmployeeForm

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    form = TransferEmployeeForm(request.POST)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    new_branch = cd.get('new_branch')
    new_dept = cd.get('new_department')

    PendingAction.objects.create(
        action_type=PendingAction.ActionType.TRANSFER,
        employee=employee,
        branch=employee.branch,
        payload={
            'transfer_date': cd['transfer_date'].isoformat(),
            'reason': cd['reason'],
            'new_branch_id': new_branch.id if new_branch else None,
            'new_department_id': new_dept.id if new_dept else None,
        },
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب النقل إلى مدير الفرع للموافقة.')
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
            days.sort()
            cleaned.append({
                'id': str(box.get('id') or f'b{idx+1}'),
                'year': year,
                'month': month,
                'days': days,
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
        emp_email = (request.POST.get('employee_email') or '').strip()
        hr_email = (request.POST.get('hr_email') or '').strip()
        recipients = [e for e in [emp_email, hr_email] if e]
        if not recipients:
            messages.warning(request, f'تم حفظ {len(cleaned)} شهر — لكن لم يتم الإرسال (لا يوجد بريد).')
            return redirect('web:view_employee', employee_id=employee.id)
        try:
            from django.template.loader import render_to_string
            from django.core.mail import EmailMultiAlternatives
            from django.conf import settings as dj_settings
            import calendar as _cal
            months_ar = ['', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                         'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
            week_days_ar = ['أحد', 'إثن', 'ثلا', 'أرب', 'خمي', 'جمع', 'سبت']
            boxes_ctx = []
            for b in cleaned:
                year, month = b['year'], b['month']
                days_set = set(b['days'])
                # Build weeks: list of 7-cell rows (Sunday-first)
                # Python: calendar.weekday() Mon=0..Sun=6 ; we want Sun=0..Sat=6
                first_wd_py = _cal.weekday(year, month, 1)  # Mon=0..Sun=6
                offset = (first_wd_py + 1) % 7  # Sun=0
                total_days = _cal.monthrange(year, month)[1]
                cells = [None] * offset + list(range(1, total_days + 1))
                while len(cells) % 7 != 0:
                    cells.append(None)
                weeks = [cells[i:i + 7] for i in range(0, len(cells), 7)]
                rows = []
                for wk in weeks:
                    rows.append([
                        {'day': d, 'on': (d in days_set) if d else False}
                        for d in wk
                    ])
                boxes_ctx.append({
                    'year': year,
                    'month': month,
                    'month_name': months_ar[month],
                    'days': b['days'],
                    'days_count': len(b['days']),
                    'days_str': '، '.join(str(d) for d in b['days']),
                    'weeks': rows,
                })
            ctx = {'employee': employee, 'boxes': boxes_ctx, 'week_days': week_days_ar}
            html_body = render_to_string('emails/employee_schedule.html', ctx)
            text_lines = [f'جدول الدوام — {employee.name}', '']
            for b in boxes_ctx:
                text_lines.append(f'{b["month_name"]} {b["year"]}: {b["days_count"]} يوم — {b["days_str"]}')
            msg = EmailMultiAlternatives(
                subject=f'جدول الدوام — {employee.name}',
                body='\n'.join(text_lines),
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.attach_alternative(html_body, 'text/html')
            msg.send(fail_silently=False)
            messages.success(request, f'تم حفظ الجدول وإرساله إلى: {", ".join(recipients)}')
        except Exception as e:
            messages.error(request, f'تم حفظ الجدول لكن فشل الإرسال: {e}')
    else:
        messages.success(request, f'تم حفظ {len(cleaned)} شهر')
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
    from apps.core.models import PendingAction
    from apps.core.forms import CustodyReceiveForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
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
    PendingAction.objects.create(
        action_type=PendingAction.ActionType.CUSTODY_RECEIVE,
        employee=employee,
        branch=employee.branch,
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
    messages.success(request, 'تم إرسال طلب استلام العهدة إلى مدير الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def clear_employee_custody(request, employee_id):
    """طلب تصفية عهدة موجودة (ينتظر دورة الموافقات)."""
    from apps.employees.models import Employee, EmployeeCustody
    from apps.core.models import PendingAction
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

    PendingAction.objects.create(
        action_type=PendingAction.ActionType.CUSTODY_CLEAR,
        employee=employee,
        branch=employee.branch,
        payload={
            'custody_id': custody.id,
            'item_name': custody.item_name,
            'returned_at': cd['returned_at'].isoformat(),
            'return_notes': cd.get('return_notes', ''),
        },
        attachment=files.get('document') or None,
        requested_by=request.user,
    )
    messages.success(request, f'تم إرسال طلب تصفية العهدة "{custody.item_name}" إلى مدير الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def add_employee_job_offer(request, employee_id):
    """طلب إصدار عرض وظيفي / خطاب تعريف (ينتظر دورة الموافقات)."""
    from apps.employees.models import Employee
    from apps.core.models import PendingAction
    from apps.core.forms import JobOfferForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = JobOfferForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    PendingAction.objects.create(
        action_type=PendingAction.ActionType.JOB_OFFER,
        employee=employee,
        branch=employee.branch,
        payload={
            'addressed_to': cd['addressed_to'],
            'purpose': cd.get('purpose', ''),
            'issued_at': cd['issued_at'].isoformat(),
            'notes': cd.get('notes', ''),
        },
        attachment=files.get('document') or None,
        requested_by=request.user,
    )
    messages.success(request, 'تم إرسال طلب العرض الوظيفي إلى مدير الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def add_employee_business_trip(request, employee_id):
    """طلب رحلة عمل (ينتظر دورة الموافقات)."""
    from apps.employees.models import Employee
    from apps.core.models import PendingAction
    from apps.core.forms import BusinessTripForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
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
    PendingAction.objects.create(
        action_type=PendingAction.ActionType.BUSINESS_TRIP,
        employee=employee,
        branch=employee.branch,
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
    messages.success(request, 'تم إرسال طلب رحلة العمل إلى مدير الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def add_employee_loan(request, employee_id):
    """تقديم سلفة موظف (ينتظر دورة الموافقات)."""
    from apps.employees.models import Employee
    from apps.core.models import PendingAction
    from apps.core.forms import LoanRequestForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
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
    PendingAction.objects.create(
        action_type=PendingAction.ActionType.LOAN_REQUEST,
        employee=employee,
        branch=employee.branch,
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
    messages.success(request, 'تم إرسال طلب السلفة إلى مدير الفرع للموافقة.')
    return redirect('web:view_employee', employee_id=employee.id)


# =============================================================================
# Roles Management
# =============================================================================



