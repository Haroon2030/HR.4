"""
نماذج الموارد البشرية الرسمية — صفحات قابلة للطباعة
Leave Request / Final Settlement / Absence Report / Employment Letter / Warning / Loan Request
"""
import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Prefetch, Q
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.utils.html import strip_tags

from apps.core.models import Company
from apps.employees.models import Employee, EmployeeLoan, EmployeeStatement, EmployeeCustody
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
        r'\(\s*مكافأة\s*([\d\.]+)\s*\+\s*إجازة\s*([\d\.]+)\s*\+\s*جزاء\s*([\d\.]+)\s*\)',
        r'\(\s*مكافأة\s*([\d\.]+)\s*\+\s*إجازة\s*([\d\.]+)\s*\)',
        r'\(\s*إجازة\s*([\d\.]+)\s*فقط\s*\)',
        r'مكافأة\s*([\d\.]+)\s*\+\s*إجازة\s*([\d\.]+)\s*\+\s*جزاء\s*([\d\.]+)',
        r'مكافأة\s*([\d\.]+)\s*\+\s*إجازة\s*([\d\.]+)',
    ):
        m = re.search(pat, text)
        if m:
            if m.re.pattern.startswith(r'\(\s*إجازة'):
                ctx['leave_comp'] = m.group(1)
                ctx['eosb_amount'] = '0'
            else:
                ctx['eosb_amount'] = m.group(1)
                ctx['leave_comp'] = m.group(2)
                if m.lastindex and m.lastindex >= 3:
                    ctx['penalty_amount'] = m.group(3)
            break

    penalty = re.search(r'شرط جزائي.*?=\s*([\d\.]+)', text)
    if penalty and 'penalty_amount' not in ctx:
        ctx['penalty_amount'] = penalty.group(1)

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


def _custody_final_settlement_context(employee) -> dict:
    """عهد نشطة للموظف — للعرض في نموذج التصفية وربط تبويب العهد."""
    active = list(
        employee.custodies.filter(status=EmployeeCustody.Status.ACTIVE)
        .order_by('-received_at', '-id')
    )
    total = Decimal('0')
    has_value = False
    for custody in active:
        if custody.estimated_value is not None and custody.estimated_value > 0:
            total += Decimal(str(custody.estimated_value))
            has_value = True
    ctx = {
        'active_custodies': active,
        'custody_active_count': len(active),
        'employee_custodies_url': (
            reverse('web:view_employee', args=[employee.id]) + '?tab=custodies'
        ),
    }
    if has_value:
        ctx['custody_total_estimated'] = str(total.quantize(Decimal('0.01')))
    return ctx


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
    penalty = Decimal(str(context.get('penalty_amount') or '0'))
    net += penalty
    if eosb > 0 or lc > 0 or ded > 0 or penalty > 0:
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
        'title': 'إنذار',
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
    from apps.core.selectors.employee_picker_search import employee_picker_queryset

    return employee_picker_queryset(user)


@login_required
@permission_required('hr_forms.view')
def hr_forms_index(request):
    """صفحة قسم النماذج الرسمية — اختيار النموذج والموظف"""
    qs = _hr_forms_employee_queryset(request.user)
    visible_forms = [f for f in HR_FORMS if hr_form_allowed_for_user(request.user, f['key'])]
    return render(request, 'pages/hr_forms/index.html', {
        'forms': visible_forms,
        'employee_total': qs.count(),
        'employee_search_url': reverse('web:hr_forms_employee_search'),
    })


@login_required
@permission_required('hr_forms.view')
def hr_forms_employee_search(request):
    """بحث موظفين للنماذج الرسمية — اقتراحات أثناء الكتابة (JSON)."""
    from apps.core.selectors.employee_picker_search import search_employees_for_picker

    q = (request.GET.get('q') or '').strip()
    results = search_employees_for_picker(request.user, q)
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

    emp_qs = Employee.objects.select_related(
        'branch', 'branch__company', 'department', 'cost_center',
        'nationality', 'profession', 'sponsorship',
    )
    if form_type == 'final_settlement':
        emp_qs = emp_qs.prefetch_related(
            Prefetch(
                'loans',
                queryset=EmployeeLoan.objects.filter(status=EmployeeLoan.Status.ACTIVE),
            ),
            Prefetch(
                'custodies',
                queryset=EmployeeCustody.objects.filter(status=EmployeeCustody.Status.ACTIVE),
            ),
            'statements_log',
        )
    elif form_type == 'warning_notice':
        emp_qs = emp_qs.annotate(
            _warning_stmt_count=Count(
                'statements_log',
                filter=Q(
                    statements_log__statement_type__in=[
                        EmployeeStatement.StatementType.WARNING,
                        EmployeeStatement.StatementType.FINAL_WARNING,
                    ]
                ),
            ),
        )
    employee = get_object_or_404(emp_qs, id=employee_id)
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
        context.update(_custody_final_settlement_context(employee))

    if form_type == 'warning_notice':
        context['warning_serial'] = EmployeeStatement.generate_serial('warning')
        context['next_statement_serial'] = EmployeeStatement.generate_serial('statement')
        context['employee_warning_no'] = getattr(employee, '_warning_stmt_count', 0) + 1

    return render(request, f'pages/hr_forms/{form_type}.html', context)
