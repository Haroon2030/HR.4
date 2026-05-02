"""طلبات التوظيف — دورة موافقات ثلاثية المراحل.

المراحل:
  1. PENDING_BRANCH  → مدير الفرع يوافق
  2. PENDING_GM      → مدير الموارد يوافق ويُسند لأخصائي
  3. PENDING_OFFICER → الأخصائي يوافق → يتم إنشاء الموظف فعلياً
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db.models import Q

from apps.core.web_views._helpers import (
    branch_manager_required,
    general_manager_required,
    hr_officer_required,
    _is_branch_manager,
    _is_general_manager,
    _is_hr_officer,
)
from apps.core.services import employment_requests as svc


User = get_user_model()


def get_hr_officers():
    """قائمة أخصائيي الموارد لقائمة الإسناد."""
    from apps.core.models import Role
    return User.objects.filter(
        is_active=True,
        profile__role__role_type=Role.RoleType.HR_OFFICER,
    ).order_by('first_name', 'username')


# ─── قائمة الطلبات ───────────────────────────────────────────────────────────
@login_required
def list_employment_requests(request):
    """قائمة طلبات التوظيف — تظهر بحسب دور المستخدم والمرحلة."""
    from apps.employees.models import EmploymentRequest

    qs = EmploymentRequest.objects.select_related(
        'branch', 'department', 'cost_center', 'requested_by',
        'branch_reviewed_by', 'gm_reviewed_by', 'assigned_officer',
    )

    user = request.user
    is_super = user.is_superuser
    is_branch = _is_branch_manager(user)
    is_gm = _is_general_manager(user)
    is_officer = _is_hr_officer(user)

    if not is_super:
        cond = Q(requested_by=user)
        if is_branch:
            managed = list(user.managed_branches.values_list('id', flat=True))
            if managed:
                cond |= Q(branch_id__in=managed)
        if is_gm:
            cond |= Q()  # المدير العام يرى الكل
            qs = qs  # سيُفلتر فقط بالحالة أدناه
            cond = Q()
        if is_officer:
            cond |= Q(assigned_officer=user)
        qs = qs.filter(cond).distinct()

    status = request.GET.get('status', 'pending')
    if status == 'pending':
        qs = qs.filter(status__in=[
            EmploymentRequest.Status.PENDING_BRANCH,
            EmploymentRequest.Status.PENDING_GM,
            EmploymentRequest.Status.PENDING_OFFICER,
            EmploymentRequest.Status.PENDING,
        ])
    elif status in {'approved', 'rejected', 'pending_branch',
                    'pending_gm', 'pending_officer'}:
        qs = qs.filter(status=status)

    return render(request, 'pages/employment_requests/list.html', {
        'requests': qs.order_by('-created_at'),
        'current_status': status,
        'is_branch_manager': is_branch,
        'is_general_manager': is_gm,
        'is_hr_officer': is_officer,
        'hr_officers': get_hr_officers() if (is_gm or is_super) else [],
    })


# ─── إجراءات المراحل ─────────────────────────────────────────────────────────
def _get_request_or_404(request_id):
    from apps.employees.models import EmploymentRequest
    return get_object_or_404(EmploymentRequest, id=request_id)


@login_required
@branch_manager_required
def approve_employment_request(request, request_id):
    """مرحلة 1: مدير الفرع يوافق → ينتقل لمدير الموارد."""
    emp_req = _get_request_or_404(request_id)

    if not request.user.is_superuser:
        managed = list(request.user.managed_branches.values_list('id', flat=True))
        if emp_req.branch_id not in managed:
            messages.error(request, 'لا تملك صلاحية مراجعة هذا الطلب')
            return redirect('web:list_employment_requests')

    if request.method != 'POST':
        return redirect('web:list_employment_requests')

    notes = request.POST.get('review_notes', '')
    try:
        svc.branch_approve(emp_req, request.user, notes=notes)
        messages.success(
            request,
            f'تمت موافقتك على طلب "{emp_req.name}" — تم تحويله لمدير الموارد البشرية'
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('web:list_employment_requests')


@login_required
@general_manager_required
def gm_approve_employment_request(request, request_id):
    """مرحلة 2: مدير الموارد يوافق ويُسند لأخصائي."""
    emp_req = _get_request_or_404(request_id)

    if request.method != 'POST':
        return redirect('web:list_employment_requests')

    officer_id = request.POST.get('assigned_officer')
    notes = request.POST.get('review_notes', '')
    if not officer_id:
        messages.error(request, 'يجب اختيار أخصائي موارد لإسناد الطلب إليه')
        return redirect('web:list_employment_requests')

    officer = User.objects.filter(id=officer_id).first()
    try:
        svc.gm_approve_and_assign(emp_req, request.user, officer, notes=notes)
        messages.success(
            request,
            f'تمت موافقتك وإسناد الطلب إلى {officer.get_full_name() or officer.username}'
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('web:list_employment_requests')


@login_required
@hr_officer_required
def officer_approve_employment_request(request, request_id):
    """مرحلة 3: الأخصائي يوافق → يُنشَأ الموظف."""
    emp_req = _get_request_or_404(request_id)

    if request.method != 'POST':
        return redirect('web:list_employment_requests')

    notes = request.POST.get('review_notes', '')
    try:
        svc.officer_approve(emp_req, request.user, notes=notes)
        messages.success(
            request,
            f'تمت الموافقة النهائية على "{emp_req.name}" وإضافته لقائمة الموظفين'
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('web:list_employment_requests')


@login_required
def reject_employment_request(request, request_id):
    """رفض نهائي للطلب — متاح بحسب الدور والمرحلة."""
    emp_req = _get_request_or_404(request_id)
    user = request.user

    can_reject = user.is_superuser
    if not can_reject:
        if _is_branch_manager(user) and emp_req.branch_id in list(
            user.managed_branches.values_list('id', flat=True)
        ):
            can_reject = True
        elif _is_general_manager(user):
            can_reject = True
        elif _is_hr_officer(user) and emp_req.assigned_officer_id == user.id:
            can_reject = True

    if not can_reject:
        messages.error(request, 'لا تملك صلاحية رفض هذا الطلب')
        return redirect('web:list_employment_requests')

    if request.method != 'POST':
        return redirect('web:list_employment_requests')

    notes = request.POST.get('review_notes', '')
    try:
        svc.reject(emp_req, user, notes=notes)
        messages.success(request, f'تم رفض طلب "{emp_req.name}"')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('web:list_employment_requests')
