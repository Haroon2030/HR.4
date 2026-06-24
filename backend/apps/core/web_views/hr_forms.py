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
    'salary_certificate': 'SC',
    'salary_transfer_commitment': 'STC',
    'permission_request': 'PR',
    'promotion': 'PM',
    'salary_adjustment': 'SA',
    'transfer': 'TR',
    'clearance': 'CL',
    'user_account': 'UA',
    'ledger_settlement': 'LS',
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

    tot = re.search(r'(?:[\*★]\s*)?صافي المستحق:\s*([\d\.]+)', text)
    if not tot:
        tot = re.search(r'(?:[\*★]\s*)?إجمالي المستحقات:\s*([\d\.]+)', text)
    if tot:
        ctx['total_entitlement'] = tot.group(1)

    prorated = re.search(r'راتب حتى [^:]+:\s*([\d\.]+)', text)
    if prorated:
        ctx['prorated_salary'] = prorated.group(1)

    loans = re.search(r'خصم سلف:\s*([\d\.]+)', text)
    if loans:
        ctx['loans_deduction'] = loans.group(1)

    absences = re.search(r'خصم غيابات:\s*([\d\.]+)', text)
    if absences:
        ctx['absences_deduction'] = absences.group(1)

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
    """إكمال الحقول الفارغة من النموذج: تعويض إجازة تقديري، سلف، غياب، راتب الفترة، صافي."""
    leave_comp, leave_days = _estimate_leave_comp_for_print(employee)
    if not context.get('leave_comp') and leave_comp is not None:
        context['leave_comp'] = leave_comp
    if not context.get('leave_days') and leave_days is not None:
        context['leave_days'] = leave_days

    loans = _active_loans_total_str(employee)
    if loans:
        context.setdefault('loans_deduction', loans)

    end = employee.end_date
    if end:
        from apps.employees.services.settlement_financials import (
            compute_settlement_financials,
            net_settlement_total,
        )

        fin = compute_settlement_financials(employee, end)
        context.setdefault('prorated_salary', str(fin['prorated_salary']))
        if fin['absences_deduction'] > 0:
            context.setdefault('absences_deduction', str(fin['absences_deduction']))
        if not context.get('loans_deduction') and fin['loans_deduction'] > 0:
            context['loans_deduction'] = str(fin['loans_deduction'])

    if context.get('total_entitlement'):
        return
    try:
        eosb = Decimal(str(context.get('eosb_amount') or '0'))
        lc = Decimal(str(context.get('leave_comp') or '0'))
        prorated = Decimal(str(context.get('prorated_salary') or '0'))
        loans_ded = Decimal(str(context.get('loans_deduction') or '0'))
        abs_ded = Decimal(str(context.get('absences_deduction') or '0'))
        penalty = Decimal(str(context.get('penalty_amount') or '0'))
    except (InvalidOperation, TypeError, ValueError):
        return
    net = eosb + lc + prorated + penalty - loans_ded - abs_ded
    if eosb > 0 or lc > 0 or prorated > 0 or loans_ded > 0 or abs_ded > 0 or penalty > 0:
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
    {
        'key': 'salary_certificate',
        'title': 'تعريف راتب',
        'print_title': 'خطاب تعريف راتب',
        'description': 'خطاب تعريف راتب للبنوك (مصرف الراجحي وغيره)',
        'icon': 'landmark',
        'color': 'indigo',
    },
    {
        'key': 'salary_transfer_commitment',
        'title': 'نموذج التزام جهة العمل بتحويل راتب الموظف',
        'description': 'نموذج التزام جهة العمل بتحويل راتب الموظف للبنك',
        'icon': 'handshake',
        'color': 'indigo',
    },
]

HR_FORMS = merge_forms_catalog(_BASE_HR_FORMS, PRIMARY_FORM_SPECS)

# نماذج بنكية — اختيار البنك من التهيئة
HR_FORMS_WITH_BANK = frozenset({
    'salary_certificate',
    'salary_transfer_commitment',
})


def _active_banks_queryset():
    from apps.setup.models import Bank

    return Bank.objects.filter(is_deleted=False, is_active=True).order_by('name')


def _banks_for_hr_form(employee):
    """بنوك التهيئة، أو بنك الموظف إن لم تُضف بنوك بعد."""
    from apps.setup.models import Bank

    qs = _active_banks_queryset()
    if qs.exists():
        return qs
    emp_bank = getattr(employee, 'bank', None)
    if emp_bank and not emp_bank.is_deleted and (emp_bank.name or '').strip():
        return Bank.objects.filter(pk=emp_bank.pk)
    return qs


def _resolve_hr_form_bank(request, employee):
    """البنك من ?bank_id= أو بنك الموظف أو أول بنك نشط في التهيئة."""
    bank_id = request.GET.get('bank_id')
    if bank_id and str(bank_id).isdigit():
        bank = _active_banks_queryset().filter(pk=int(bank_id)).first()
        if bank:
            return bank

    emp_bank = getattr(employee, 'bank', None)
    if emp_bank and not emp_bank.is_deleted and emp_bank.is_active:
        return emp_bank

    return _active_banks_queryset().first()


def _active_professions_queryset():
    from apps.setup.models import Profession

    return Profession.objects.filter(is_deleted=False, is_active=True).order_by('name')


def _professions_for_hr_form(employee):
    """مهن التهيئة، مع مهنة الموظف إن لم تكن ضمن القائمة النشطة."""
    from apps.setup.models import Profession

    items = list(_active_professions_queryset())
    emp_prof = getattr(employee, 'profession', None)
    if emp_prof and emp_prof.pk and not any(p.pk == emp_prof.pk for p in items):
        if not emp_prof.is_deleted and (emp_prof.name or '').strip():
            items.append(emp_prof)
    return items


def _resolve_hr_form_profession(request, employee):
    """المهنة من ?profession_id= أو مهنة الموظف."""
    profession_id = request.GET.get('profession_id')
    if profession_id and str(profession_id).isdigit():
        prof = _active_professions_queryset().filter(pk=int(profession_id)).first()
        if prof:
            return prof
        from apps.setup.models import Profession
        prof = Profession.objects.filter(pk=int(profession_id), is_deleted=False).first()
        if prof:
            return prof

    emp_prof = getattr(employee, 'profession', None)
    if emp_prof and not emp_prof.is_deleted:
        return emp_prof
    return None


def _resolve_hr_form_hire_date(request, employee):
    """تاريخ الالتحاق من ?hire_date= أو ملف الموظف."""
    from datetime import date as date_cls

    raw = (request.GET.get('hire_date') or '').strip()
    if raw:
        try:
            return date_cls.fromisoformat(raw)
        except ValueError:
            pass
    return getattr(employee, 'hire_date', None)


def _resolve_employee_sponsorship(employee):
    """كفالة الموظف (حقل «الشركة» في ملف الموظف) — حتى لو لم تُحمَّل عبر select_related."""
    from apps.setup.models import Sponsorship

    sid = getattr(employee, 'sponsorship_id', None)
    if not sid:
        return None
    cached = getattr(employee, 'sponsorship', None)
    if cached is not None:
        return cached
    return Sponsorship.all_objects.filter(pk=sid).first()


def _letterhead_context(employee, company) -> dict:
    """اسم المنشأة والسجل التجاري — من كفالة الموظف ثم شركة الفرع."""
    sponsorship = _resolve_employee_sponsorship(employee)
    if sponsorship and not getattr(sponsorship, 'is_deleted', False):
        name = (sponsorship.company_name or '').strip()
        if name:
            cr = (sponsorship.commercial_registration or '').strip()
            if not cr:
                branch_co = None
                if getattr(employee, 'branch_id', None):
                    branch = getattr(employee, 'branch', None)
                    if branch and getattr(branch, 'company_id', None):
                        branch_co = branch.company
                employer_co = branch_co or company
                if employer_co:
                    cr = (getattr(employer_co, 'commercial_record', None) or '').strip()
            return {
                'letterhead_name': name,
                'letterhead_cr': cr,
                'letterhead_source': 'sponsorship',
                'employee_sponsorship': sponsorship,
            }

    branch_company = None
    if getattr(employee, 'branch_id', None):
        branch = getattr(employee, 'branch', None)
        if branch and getattr(branch, 'company_id', None):
            branch_company = branch.company

    employer = branch_company or company
    if employer:
        name = (employer.name or '').strip()
        if name:
            return {
                'letterhead_name': name,
                'letterhead_cr': (getattr(employer, 'commercial_record', None) or '').strip(),
                'letterhead_source': 'company',
                'employee_sponsorship': sponsorship,
            }

    return {
        'letterhead_name': '',
        'letterhead_cr': '',
        'letterhead_source': '',
        'employee_sponsorship': sponsorship,
    }


DEFAULT_LETTER_FOOTER_AR = (
    'المملكة العربية السعودية - الرياض - حي الريان - ص.ب 260778 '
    'الرمز البريدي 11342 هاتف 4916286 - فاكس 4970476 - تحويله 110'
)
DEFAULT_LETTER_FOOTER_EN = (
    'Kingdom of Saudi Arabia - Riyadh - Al Rayan Area - P.O Box 260778 '
    'code/11342 Tel/4916286 fax/4970476 Ext/110'
)


def _letter_footer_context(company) -> dict:
    """تذييل الخطاب الرسمي (عربي + إنجليزي) — أسفل صفحة الطباعة."""
    ar = ''
    en = ''
    if company:
        ar = (getattr(company, 'letter_footer_ar', None) or '').strip()
        en = (getattr(company, 'letter_footer_en', None) or '').strip()
    return {
        'letter_footer_ar': ar or DEFAULT_LETTER_FOOTER_AR,
        'letter_footer_en': en or DEFAULT_LETTER_FOOTER_EN,
    }


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
        'banks': list(_active_banks_queryset().values('id', 'name')),
        'has_bank_forms': any(f['key'] in HR_FORMS_WITH_BANK for f in visible_forms),
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
        'nationality', 'profession', 'sponsorship', 'bank',
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
    context.update(_letterhead_context(employee, company))
    context.update(_letter_footer_context(company))

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

    if form_type in HR_FORMS_WITH_BANK:
        context['bank'] = _resolve_hr_form_bank(request, employee)
        context['banks'] = _banks_for_hr_form(employee)

    context['profession'] = _resolve_hr_form_profession(request, employee)
    context['professions'] = _professions_for_hr_form(employee)
    context['form_hire_date'] = _resolve_hr_form_hire_date(request, employee)
    context['form_employee_iban'] = (getattr(employee, 'iban', None) or '').strip()

    if form_type == 'salary_transfer_commitment':
        # نموذج البنك: حقول يدوية فارغة — لا تُسحب من ملف الموظف (ما عدا الاسم)
        context['form_work_id'] = ''
        context['form_employee_iban'] = ''
        context['eosb_entitlement'] = None
        context['eosb_resignation'] = None

    return render(request, f'pages/hr_forms/{form_type}.html', context)


@login_required
@permission_required('employees.view')
@employee_branch_access_required
def print_ledger_settlement_detail(request, employee_id, ledger_id):
    """نموذج رسمي قابل للطباعة — تفاصيل حركة المخصصات بعنوان تصفية نهاية الخدمة."""
    from apps.core.salary_access import user_can_view_salary
    from apps.employees.models import EmployeeLedger

    if not user_can_view_salary(request.user):
        messages.error(request, 'لا تملك صلاحية عرض بيانات الراتب والمخصصات.')
        return redirect('web:view_employee', employee_id=employee_id)

    employee = get_object_or_404(
        Employee.objects.select_related(
            'branch', 'branch__company', 'department', 'nationality', 'sponsorship',
        ),
        id=employee_id,
    )
    ledger = get_object_or_404(
        EmployeeLedger.objects.filter(employee=employee),
        id=ledger_id,
    )
    company = (employee.branch.company if employee.branch_id else None) or Company.objects.first()

    form_meta = {
        'key': 'ledger_settlement',
        'title': 'تصفية نهاية الخدمة',
        'print_title': 'تصفية نهاية الخدمة',
    }
    context = {
        'form_meta': form_meta,
        'employee': employee,
        'ledger': ledger,
        'company': company,
        'branch': employee.branch,
        'form_serial': _build_form_serial('ledger_settlement', employee.id),
        'form_back_url': reverse('web:view_employee', args=[employee.id]) + '?tab=accruals',
    }
    context.update(_letterhead_context(employee, company))
    context.update(_letter_footer_context(company))
    return render(request, 'pages/hr_forms/ledger_settlement_detail.html', context)
