"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from functools import wraps

from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.web_views._helpers import (
    admin_required, _is_branch_manager, branch_manager_required,
    _user_accessible_branch_ids, employee_branch_access_required, _can_review_action,
)

@login_required
@branch_manager_required
def list_employment_requests(request):
    """قائمة طلبات التوظيف للفروع التي يديرها المستخدم"""
    from apps.employees.models import EmploymentRequest

    qs = EmploymentRequest.objects.select_related(
        'branch', 'department', 'cost_center', 'requested_by'
    )
    if not request.user.is_superuser:
        managed = request.user.managed_branches.values_list('id', flat=True)
        qs = qs.filter(branch_id__in=list(managed))

    status = request.GET.get('status', 'pending')
    if status in {'pending', 'approved', 'rejected'}:
        qs = qs.filter(status=status)

    return render(request, 'pages/employment_requests/list.html', {
        'requests': qs.order_by('-created_at'),
        'current_status': status,
    })


@login_required
@branch_manager_required
def approve_employment_request(request, request_id):
    """الموافقة على طلب توظيف وإنشاء سجل موظف تلقائياً"""
    from django.utils import timezone
    from apps.employees.models import EmploymentRequest, Employee

    emp_request = get_object_or_404(EmploymentRequest, id=request_id)

    # تحقق من صلاحية المراجعة (يجب أن يكون مديراً لفرع الطلب)
    if not request.user.is_superuser:
        if emp_request.branch_id not in list(
            request.user.managed_branches.values_list('id', flat=True)
        ):
            messages.error(request, 'لا تملك صلاحية مراجعة هذا الطلب')
            return redirect('web:list_employment_requests')

    if emp_request.status != EmploymentRequest.Status.PENDING:
        messages.warning(request, 'تم البت في هذا الطلب مسبقاً')
        return redirect('web:list_employment_requests')

    if request.method == 'POST':
        from apps.core.forms import ReviewNotesForm
        notes_form = ReviewNotesForm(request.POST)
        notes_form.is_valid()
        emp_request.status = EmploymentRequest.Status.APPROVED
        emp_request.reviewed_by = request.user
        emp_request.reviewed_at = timezone.now()
        emp_request.review_notes = notes_form.cleaned_data.get('review_notes', '')
        emp_request.save()

        # إنشاء سجل موظف مرتبط بالطلب
        Employee.objects.create(
            name=emp_request.name,
            branch=emp_request.branch,
            department=emp_request.department,
            cost_center=emp_request.cost_center,
            commencement_document=emp_request.commencement_document,
            employment_request=emp_request,
            status=Employee.Status.ACTIVE,
        )

        messages.success(request, f'تمت الموافقة على طلب "{emp_request.name}" وإضافته لقائمة الموظفين')

    return redirect('web:list_employment_requests')


@login_required
@branch_manager_required
def reject_employment_request(request, request_id):
    """رفض طلب توظيف"""
    from django.utils import timezone
    from apps.employees.models import EmploymentRequest

    emp_request = get_object_or_404(EmploymentRequest, id=request_id)

    if not request.user.is_superuser:
        if emp_request.branch_id not in list(
            request.user.managed_branches.values_list('id', flat=True)
        ):
            messages.error(request, 'لا تملك صلاحية مراجعة هذا الطلب')
            return redirect('web:list_employment_requests')

    if emp_request.status != EmploymentRequest.Status.PENDING and request.method == 'POST':
        messages.warning(request, 'تم البت في هذا الطلب مسبقاً')
        return redirect('web:list_employment_requests')

    if request.method == 'POST':
        from apps.core.forms import ReviewNotesForm
        notes_form = ReviewNotesForm(request.POST)
        notes_form.is_valid()
        emp_request.status = EmploymentRequest.Status.REJECTED
        emp_request.reviewed_by = request.user
        emp_request.reviewed_at = timezone.now()
        emp_request.review_notes = notes_form.cleaned_data.get('review_notes', '')
        emp_request.save()
        messages.success(request, f'تم رفض طلب "{emp_request.name}"')

    return redirect('web:list_employment_requests')


# =============================================================================
# Edit Employee (الأخصائي يكمل بقية الحقول)
# =============================================================================
