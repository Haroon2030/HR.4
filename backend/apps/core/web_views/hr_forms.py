"""
نماذج الموارد البشرية الرسمية — صفحات قابلة للطباعة
Leave Request / Final Settlement / Absence Report / Employment Letter / Warning / Loan Request
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404

from apps.core.models import Company
from apps.employees.models import Employee
from apps.core.web_views._helpers import admin_required


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
        'title': 'مخالصة نهاية الخدمة',
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
]


@login_required
@admin_required
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
@admin_required
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
