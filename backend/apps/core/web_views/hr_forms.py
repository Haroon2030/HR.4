"""
نماذج الموارد البشرية الرسمية — صفحات قابلة للطباعة
Leave Request / Final Settlement / Absence Report / Employment Letter / Warning / Loan Request
"""
import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.utils.html import strip_tags

from apps.core.models import Company
from apps.employees.models import Employee, EmployeeLoan, EmployeeStatement
from django.contrib import messages

from apps.core.decorators import permission_required
from apps.core.permission_policy import hr_form_allowed_for_user
from apps.core.web_views._helpers import employee_branch_access_required
from apps.core.services.hr_forms_catalog import PRIMARY_FORM_SPECS, merge_forms_catalog


# اختصارات قصيرة لكود النموذج تظهر في السريال (لو ما وجد، يُؤخذ أول 3 حروف من الـ key)
FORM_CODE_MAP = {
    'leave_request': 'LR',
    'final_settlement': 'FS',
    'warning_notice': 'WN',
    'loan_request': 'LN',
    'custody_receipt': 'CR',
    'custody_clearance': 'CC',
    'evaluation': 'EV',
    'resumption_after_leave': 'RL',
    'contract_termination': 'CT',
    'absence_report': 'AR',
    'employment_letter': 'EL',
    'permission_request': 'PR',
    'promotion': 'PM',
    'salary_adjustment': 'SA',
    'transfer': 'TR',
    'clearance': 'CL',
    'user_account': 'UA',
}


def _build_form_serial(form_type, employee_id):
    """
    يولّد رقم نموذج تقني فريد بصيغة: <CODE>-<YYMMDD>-<EMP4>-<HASH4>
    مثال: LR-260512-0005-A3F2
    """
    code = FORM_CODE_MAP.get(form_type, form_type[:3].upper())
    now = datetime.now()
    date_part = now.strftime('%y%m%d')
    emp_part = f"{int(employee_id):04d}"
    raw = f"{form_type}-{employee_id}-{now.strftime('%Y%m%d%H%M%S%f')}"
    hash_part = hashlib.sha1(raw.encode()).hexdigest()[:4].upper()
    return f"{code}-{date_part}-{emp_part}-{hash_part}"


def _parse_final_settlement_statement(content: str) -> dict:
    """يستخرج أرقام التصفية من نص إفادة التصفية (مع تسامح مع ★ ومسافات وHTML)."""
    ctx: dict = {}
    if not content or not str(content).strip():
        return ctx
    text = strip_tags(str(content))
    text = text.replace('\r\n', '\n').replace('\u00a0', ' ')

    for pat in (
        r'\(\s*مكافأة\s*([\d\.]+)\s*\+\s*إجازة\s*([\d\.]+)\s*\)',
        r'مكافأة\s*([\d\.]+)\s*\+\s*إجازة\s*([\d\.]+)',
    ):
        m = re.search(pat, text)
        if m:
            ctx['eosb_amount'] = m.group(1)
            ctx['leave_comp'] = m.group(2)
            break

    tot = re.search(r'(?:[\*★]\s*)?إجمالي المستحقات:\s*([\d\.]+)', text)
    if tot:
        ctx['total_entitlement'] = tot.group(1)

    srv = re.search(r'مدة الخدمة:\s*([^\n]+)', text)
    if srv:
        ctx['service_duration'] = srv.group(1).strip()

    ld = re.search(r'رصيد الإجازة:\s*([\d\.]+)\s*يوم', text)
    if ld:
        ctx['leave_days'] = ld.group(1)

    return ctx


def _estimate_leave_comp_for_print(employee) -> tuple[str | None, str | None]:
    """تعويض إجازة تقديري من الراتب الحالي ورصيد الأيام (نفس منطق المسير عند وجود كفالة)."""
    if not employee.sponsorship_id:
        return None, None
    try:
        last = Decimal(str(employee.total_salary or 0))
    except (InvalidOperation, TypeError, ValueError):
        return None, None
    if last <= 0:
        return None, None
    try:
        days = Decimal(str(employee.remaining_leave_days or 0))
    except (InvalidOperation, TypeError, ValueError):
        return None, None
    from apps.core.salary_month import daily_rate_from_total
    daily = daily_rate_from_total(last)
    comp = (daily * days).quantize(Decimal('0.01'))
    return str(comp), str(days.quantize(Decimal('0.1')))


def _active_loans_total_str(employee) -> str | None:
    total = Decimal('0')
    for loan in employee.loans.filter(status=EmployeeLoan.Status.ACTIVE):
        rb = loan.remaining_balance
        if rb and rb > 0:
            total += Decimal(str(rb))
    if total <= 0:
        return None
    return str(total.quantize(Decimal('0.01')))


def _apply_final_settlement_fallbacks(employee, context: dict) -> None:
    """إكمال الحقول الفارغة من النموذج: تعويض إجازة تقديري، سلف، صافي عند غياب سطر الإجمالي."""
    leave_comp, leave_days = _estimate_leave_comp_for_print(employee)
    if not context.get('leave_comp') and leave_comp is not None:
        context['leave_comp'] = leave_comp
    if not context.get('leave_days') and leave_days is not None:
        context['leave_days'] = leave_days

    loans = _active_loans_total_str(employee)
    if loans:
        context['loans_deduction'] = loans

    if context.get('total_entitlement'):
        return
    try:
        eosb = Decimal(str(context.get('eosb_amount') or '0'))
        lc = Decimal(str(context.get('leave_comp') or '0'))
        ded = Decimal(str(context.get('loans_deduction') or '0'))
    except (InvalidOperation, TypeError, ValueError):
        return
    net = eosb + lc - ded
    if eosb > 0 or lc > 0 or ded > 0:
        context['total_entitlement'] = str(net.quantize(Decimal('0.01')))


# قائمة النماذج المعتمدة
_BASE_HR_FORMS = [
    {
        'key': 'leave_request',
        'title': 'طلب إجازة',
        'description': 'نموذج رسمي لتقديم طلب إجازة (سنوية / مرضية / اضطرارية)',
        'icon': 'plane',
        'color': 'emerald',
    },
    {
        'key': 'final_settlement',
        'title': 'تصفية نهاية خدمة',
        'description': 'إقرار وإخلاء طرف بنهاية خدمة الموظف',
        'icon': 'file-check',
        'color': 'amber',
    },
    {
        'key': 'warning_notice',
        'title': 'إنذار / مخالفة',
        'description': 'إشعار رسمي بمخالفة أو إنذار للموظف',
        'icon': 'alert-triangle',
        'color': 'amber',
    },
    {
        'key': 'loan_request',
        'title': 'طلب سلفة',
        'description': 'نموذج رسمي لطلب سلفة على الراتب',
        'icon': 'wallet',
        'color': 'primary',
    },
    {
        'key': 'custody_receipt',
        'title': 'استلام عهدة',
        'description': 'إقرار باستلام الموظف لعهدة من الشركة',
        'icon': 'package-check',
        'color': 'emerald',
    },
    {
        'key': 'custody_clearance',
        'title': 'تصفية عهدة',
        'description': 'إخلاء طرف من العهدة وإعادة الأصول للشركة',
        'icon': 'package-x',
        'color': 'rose',
    },
    {
        'key': 'evaluation',
        'title': 'تقييم موظف',
        'description': 'نموذج رسمي لتقييم أداء الموظف',
        'icon': 'clipboard-check',
        'color': 'cyan',
    },
    {
        'key': 'resumption_after_leave',
        'title': 'مباشرة بعد الإجازة',
        'description': 'إثبات مباشرة الموظف للعمل بعد انتهاء إجازته',
        'icon': 'log-in',
        'color': 'emerald',
    },
    {
        'key': 'contract_termination',
        'title': 'إنهاء عقد',
        'description': 'إشعار رسمي بإنهاء عقد العمل',
        'icon': 'file-x',
        'color': 'rose',
    },
]

HR_FORMS = merge_forms_catalog(_BASE_HR_FORMS, PRIMARY_FORM_SPECS)


def _hr_forms_employee_queryset(user):
    """موظفون المتاحون للنماذج — فلترة الفرع ثم الترتيب (لا slice قبل الفلترة)."""
    from apps.core.web_views._helpers import filter_employees_queryset_for_user

    qs = Employee.objects.filter(is_deleted=False).select_related(
        'branch', 'department', 'profession',
    )
    qs = filter_employees_queryset_for_user(user, qs)
    return qs.order_by('name')


@login_required
@permission_required('hr_forms.view')
def hr_forms_index(request):
    """صفحة قسم النماذج الرسمية — اختيار النموذج والموظف"""
    qs = _hr_forms_employee_queryset(request.user)
    visible_forms = [f for f in HR_FORMS if hr_form_allowed_for_user(request.user, f['key'])]
    return render(request, 'pages/hr_forms/index.html', {
        'forms': visible_forms,
        'employees': list(qs[:500]),
        'employee_total': qs.count(),
        'employee_search_url': reverse('web:hr_forms_employee_search'),
    })


@login_required
@permission_required('hr_forms.view')
def hr_forms_employee_search(request):
    """بحث موظفين للنماذج الرسمية — اقتراحات أثناء الكتابة (JSON)."""
    from django.db.models import Q
    from django.http import JsonResponse

    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse({'results': [], 'total': 0})

    qs = _hr_forms_employee_queryset(request.user)
    terms = [t for t in q.split() if t]
    if terms:
        cond = Q()
        for t in terms:
            cond &= (
                Q(name__icontains=t)
                | Q(id_number__icontains=t)
                | Q(employee_number__icontains=t)
                | Q(phone__icontains=t)
                | Q(branch__name__icontains=t)
                | Q(department__name__icontains=t)
                | Q(profession__name__icontains=t)
            )
        qs = qs.filter(cond)

    results = [
        {
            'id': emp.id,
            'name': emp.name,
            'number': emp.employee_number or '',
            'id_number': emp.id_number or '',
            'dept': emp.department.name if emp.department_id else '',
            'branch': emp.branch.name if emp.branch_id else '',
        }
        for emp in qs[:40]
    ]
    return JsonResponse({'results': results, 'total': len(results)})


@login_required
@permission_required('hr_forms.view')
@employee_branch_access_required
def hr_form_print(request, form_type, employee_id):
    """عرض نموذج رسمي قابل للطباعة لموظف محدد"""
    form_meta = next((f for f in HR_FORMS if f['key'] == form_type), None)
    if not form_meta:
        raise Http404("نموذج غير معروف")
    if not hr_form_allowed_for_user(request.user, form_type):
        messages.error(request, 'لا تملك صلاحية عرض نماذج تحتوي بيانات الرواتب.')
        return redirect('web:hr_forms_index')

    employee = get_object_or_404(
        Employee.objects.select_related(
            'branch', 'branch__company', 'department', 'cost_center',
            'nationality', 'profession', 'sponsorship',
        ),
        id=employee_id,
    )
    company = (employee.branch.company if employee.branch_id else None) or Company.objects.first()

    context = {
        'form_meta': form_meta,
        'employee': employee,
        'company': company,
        'branch': employee.branch,
        'form_serial': _build_form_serial(form_type, employee.id),
    }

    if form_type in ('custody_clearance', 'custody_receipt'):
        from apps.setup.models import Administration
        context['administrations'] = Administration.objects.filter(
            is_deleted=False, is_active=True,
        ).order_by('code', 'name')

    if form_type == 'final_settlement':
        stmt_id = request.GET.get('stmt_id')
        if stmt_id and stmt_id.isdigit():
            stmt = employee.statements_log.filter(id=stmt_id).first()
        else:
            stmt = employee.statements_log.filter(
                statement_type=EmployeeStatement.StatementType.TERMINATE,
            ).last()

        if stmt and (stmt.content or '').strip():
            context.update(_parse_final_settlement_statement(stmt.content))
        _apply_final_settlement_fallbacks(employee, context)

    return render(request, f'pages/hr_forms/{form_type}.html', context)
