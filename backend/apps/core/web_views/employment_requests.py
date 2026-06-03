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
    _is_branch_manager,
    _is_general_manager,
    _is_hr_officer,
)
from apps.core.models import PendingAction
from apps.core.services.workflow_access import stage_permission_required
from apps.core.services import employment_requests as svc
from apps.core.services.approval_routing import first_stage_pending_q, resolve_first_approver, user_can_first_approve, first_stage_tab_label


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
    from apps.core.services.workflow_access import can_view_operations
    from apps.employees.models import EmploymentRequest

    if not can_view_operations(request.user):
        messages.error(request, 'لا تملك صلاحية عرض طلبات التوظيف.')
        return redirect('web:dashboard')

    qs = EmploymentRequest.objects.select_related(
        'branch', 'administration', 'department', 'cost_center', 'requested_by',
        'branch_reviewed_by', 'gm_reviewed_by', 'assigned_officer',
        'housing', 'bank',
    )

    user = request.user
    is_super = user.is_superuser
    is_branch = _is_branch_manager(user)
    is_gm = _is_general_manager(user)
    is_officer = _is_hr_officer(user)

    if not is_super:
        cond = Q(requested_by=user)
        if is_branch:
            cond |= first_stage_pending_q(
                user,
                model_status_pending_branch=EmploymentRequest.Status.PENDING_BRANCH,
            )
        if is_gm:
            # المدير العام يرى الكل — أبطل الفلترة على الملكية/الفرع
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

    from django.core.paginator import Paginator

    paginator = Paginator(qs.order_by('-created_at'), 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    for row in page_obj.object_list:
        row.first_stage_label = resolve_first_approver(row).stage_label

    return render(request, 'pages/employment_requests/list.html', {
        'requests': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'current_status': status,
        'is_branch_manager': is_branch,
        'is_general_manager': is_gm,
        'is_hr_officer': is_officer,
        'hr_officers': get_hr_officers() if (is_gm or is_super) else [],
        'first_stage_tab_label': first_stage_tab_label(user),
    })


# ─── إجراءات المراحل ─────────────────────────────────────────────────────────
def _get_request_or_404(request_id):
    from apps.employees.models import EmploymentRequest
    return get_object_or_404(EmploymentRequest, id=request_id)


@login_required
def approve_employment_request(request, request_id):
    """مرحلة 1: مدير الإدارة/الفرع يوافق → ينتقل لمدير الموارد."""
    emp_req = _get_request_or_404(request_id)

    if not user_can_first_approve(request.user, emp_req):
        messages.error(request, 'لا تملك صلاحية مراجعة هذا الطلب')
        return redirect('web:list_employment_requests')

    if request.method != 'POST':
        return redirect('web:list_employment_requests')

    if not stage_permission_required(request.user, PendingAction.Stage.BRANCH):
        messages.error(request, 'لا تملك صلاحية الموافقة على هذه المرحلة.')
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
def gm_approve_employment_request(request, request_id):
    """مرحلة 2: مدير الموارد يوافق ويُسند لأخصائي."""
    emp_req = _get_request_or_404(request_id)

    if request.method != 'POST':
        return redirect('web:list_employment_requests')

    from apps.employees.models import EmploymentRequest
    if emp_req.status != EmploymentRequest.Status.PENDING_GM:
        messages.error(request, 'لا يمكن الموافقة على هذا الطلب في مرحلته الحالية.')
        return redirect('web:list_employment_requests')

    if not stage_permission_required(request.user, PendingAction.Stage.GM):
        messages.error(request, 'لا تملك صلاحية الموافقة كمدير عام.')
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
def officer_approve_employment_request(request, request_id):
    """مرحلة 3: الأخصائي يوافق → يُنشَأ الموظف."""
    emp_req = _get_request_or_404(request_id)

    if request.method != 'POST':
        return redirect('web:list_employment_requests')

    if (
        emp_req.assigned_officer_id != request.user.id
        and not request.user.is_superuser
    ):
        messages.error(request, 'هذا الطلب غير مُسند إليك.')
        return redirect('web:list_employment_requests')

    if not stage_permission_required(request.user, PendingAction.Stage.OFFICER):
        messages.error(request, 'لا تملك صلاحية التنفيذ.')
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

    from apps.core.services.workflow_access import user_can_reject_employment_request

    if not user_can_reject_employment_request(user, emp_req):
        messages.error(request, 'لا تملك صلاحية رفض/إرجاع هذا الطلب.')
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


# ─── تعديل بيانات الموظف على الطلب (قبل الموافقة النهائية) ──────────────
@login_required
def edit_employment_request(request, request_id):
    """صفحة لإكمال بيانات الموظف على طلب التوظيف قبل الموافقة النهائية.

    متاحة فقط للأخصائي المُسند (أو superuser) عندما تكون الحالة
    PENDING_OFFICER.
    """
    from apps.employees.models import EmploymentRequest
    from apps.employees.forms import EmploymentRequestEditForm

    emp_req = _get_request_or_404(request_id)

    # تحقق من المرحلة
    if emp_req.status != EmploymentRequest.Status.PENDING_OFFICER:
        messages.error(request, 'لا يمكن تعديل البيانات في هذه المرحلة.')
        return redirect('web:list_employment_requests')

    # تحقق من الإسناد + صلاحية التنفيذ
    if emp_req.assigned_officer_id != request.user.id and not request.user.is_superuser:
        messages.error(request, 'هذا الطلب غير مُسند إليك.')
        return redirect('web:list_employment_requests')
    if not stage_permission_required(request.user, PendingAction.Stage.OFFICER):
        messages.error(request, 'لا تملك صلاحية تعديل بيانات هذا الطلب.')
        return redirect('web:list_employment_requests')

    if request.method == 'POST':
        form = EmploymentRequestEditForm(request.POST, request.FILES, instance=emp_req)
        if form.is_valid():
            form.save()
            # هل المستخدم ضغط "حفظ والموافقة"؟
            if request.POST.get('action') == 'save_and_approve':
                try:
                    svc.officer_approve(emp_req, request.user,
                                        notes=request.POST.get('review_notes', ''))
                    messages.success(
                        request,
                        f'تم حفظ البيانات والموافقة النهائية على "{emp_req.name}".'
                    )
                    return redirect('web:list_employment_requests')
                except ValueError as e:
                    messages.error(request, str(e))
                    # نبقى في صفحة التعديل
            else:
                messages.success(request, f'تم حفظ بيانات "{emp_req.name}" بنجاح.')
                return redirect('web:edit_employment_request', request_id=emp_req.id)
        else:
            messages.error(request, 'يوجد أخطاء في النموذج، يرجى مراجعة الحقول.')
    else:
        form = EmploymentRequestEditForm(instance=emp_req)

    # عرض الحقول الناقصة كتنبيه
    missing = svc.validate_employee_data_complete(emp_req)

    return render(request, 'pages/employment_requests/edit.html', {
        'form': form,
        'emp_req': emp_req,
        'missing_fields': missing,
        'title': f'تعديل بيانات الموظف — {emp_req.name}',
    })

