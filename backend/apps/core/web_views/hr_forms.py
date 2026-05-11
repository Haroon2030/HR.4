"""
نماذج الموارد البشرية الرسمية — صفحات قابلة للطباعة
Leave Request / Final Settlement / Absence Report / Employment Letter / Warning / Loan Request
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404

from apps.core.models import Company
from apps.employees.models import Employee
from apps.core.decorators import permission_required


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

    return render(request, f'pages/hr_forms/{form_type}.html', {
        'form_meta': form_meta,
        'employee': employee,
        'company': company,
        'branch': employee.branch,
    })
