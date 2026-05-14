"""
نماذج الموارد البشرية الرسمية — صفحات قابلة للطباعة
Leave Request / Final Settlement / Absence Report / Employment Letter / Warning / Loan Request
"""
import hashlib
from datetime import datetime

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404

from apps.core.models import Company
from apps.employees.models import Employee
from apps.core.decorators import permission_required


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
    'business_trip': 'BT',
    'absence_report': 'AR',
    'employment_letter': 'EL',
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


# قائمة النماذج المعتمدة
HR_FORMS = [
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
    {
        'key': 'business_trip',
        'title': 'رحلة عمل',
        'description': 'إذن وتفاصيل رحلة عمل رسمية للموظف',
        'icon': 'plane-takeoff',
        'color': 'primary',
    },
]


@login_required
@permission_required('hr_forms.view')
def hr_forms_index(request):
    """صفحة قسم النماذج الرسمية — اختيار النموذج والموظف"""
    employees = (
        Employee.objects.filter(is_deleted=False)
        .select_related('branch', 'department', 'profession')
        .order_by('name')
    )
    return render(request, 'pages/hr_forms/index.html', {
        'forms': HR_FORMS,
        'employees': employees,
    })


@login_required
@permission_required('hr_forms.view')
def hr_form_print(request, form_type, employee_id):
    """عرض نموذج رسمي قابل للطباعة لموظف محدد"""
    form_meta = next((f for f in HR_FORMS if f['key'] == form_type), None)
    if not form_meta:
        raise Http404("نموذج غير معروف")

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

    if form_type == 'final_settlement':
        stmt = employee.statements_log.filter(statement_type='terminate').last()
        if stmt:
            import re
            m = re.search(r'\(مكافأة ([\d\.]+) \+ إجازة ([\d\.]+)\)', stmt.content)
            if m:
                context['eosb_amount'] = m.group(1)
                context['leave_comp'] = m.group(2)
            tot = re.search(r'إجمالي المستحقات:\s*([\d\.]+)', stmt.content)
            if tot:
                context['total_entitlement'] = tot.group(1)
            srv = re.search(r'مدة الخدمة:\s*(.*?)$', stmt.content, re.MULTILINE)
            if srv:
                context['service_duration'] = srv.group(1).strip()
            
            # Extract leave days
            ld = re.search(r'رصيد الإجازة:\s*([\d\.]+) يوم', stmt.content)
            if ld:
                context['leave_days'] = ld.group(1)

    return render(request, f'pages/hr_forms/{form_type}.html', context)
