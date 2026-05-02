"""
Pending Actions — Views (دورة موافقات متعدّدة المراحل)
======================================================
المراحل:
    1) الأخصائي ينشئ → pending_branch
    2) مدير الفرع يوافق → pending_gm           [branch_approve_action]
    3) المدير العام يوافق ويُسند موظف موارد → pending_officer  [gm_approve_action]
    4) موظف الموارد يوافق فيُنفَّذ تلقائياً → approved          [officer_approve_action]

    + return_pending_action  — إرجاع للأخصائي من أي مرحلة
    + resubmit_pending_action — الأخصائي يعيد الإرسال بعد التعديل
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import PendingAction, Role
from apps.core.web_views._helpers import (
    _can_act_at_stage,
    _is_branch_manager,
    _is_general_manager,
    _is_hr_officer,
)


# =============================================================================
# قائمة الطلبات (مفلترة حسب الدور)
# =============================================================================

TAB_FILTERS = {
    'inbox': None,
    'pending_branch': PendingAction.Status.PENDING_BRANCH,
    'pending_gm': PendingAction.Status.PENDING_GM,
    'pending_officer': PendingAction.Status.PENDING_OFFICER,
    'returned': PendingAction.Status.RETURNED,
    'approved': PendingAction.Status.APPROVED,
    'mine': None,
}


def _user_visible_actions(user):
    qs = PendingAction.objects.select_related(
        'employee', 'branch', 'requested_by',
        'branch_reviewed_by', 'gm_reviewed_by', 'assigned_officer', 'returned_by',
    )
    if user.is_superuser or _is_general_manager(user):
        return qs

    filters = Q(requested_by=user)
    managed_ids = list(user.managed_branches.values_list('id', flat=True))
    if managed_ids:
        filters |= Q(branch_id__in=managed_ids)
    if _is_hr_officer(user):
        filters |= Q(assigned_officer=user)
    return qs.filter(filters).distinct()


def _inbox_for(user, qs):
    f = Q()
    has_filter = False
    if user.is_superuser or _is_general_manager(user):
        f |= Q(status=PendingAction.Status.PENDING_GM)
        has_filter = True
    if _is_branch_manager(user):
        managed_ids = list(user.managed_branches.values_list('id', flat=True))
        if managed_ids:
            f |= Q(status=PendingAction.Status.PENDING_BRANCH, branch_id__in=managed_ids)
            has_filter = True
    if user.is_superuser:
        f |= Q(status=PendingAction.Status.PENDING_BRANCH)
        has_filter = True
    if _is_hr_officer(user) or user.is_superuser:
        f |= Q(status=PendingAction.Status.PENDING_OFFICER, assigned_officer=user) \
            if not user.is_superuser \
            else Q(status=PendingAction.Status.PENDING_OFFICER)
        has_filter = True
    f |= Q(status=PendingAction.Status.RETURNED, requested_by=user)
    return qs.filter(f) if has_filter or True else qs.none()


@login_required
def list_pending_actions(request):
    tab = request.GET.get('tab', 'inbox')
    base = _user_visible_actions(request.user)

    if tab == 'inbox':
        qs = _inbox_for(request.user, base)
    elif tab == 'mine':
        qs = base.filter(requested_by=request.user)
    elif tab in TAB_FILTERS and TAB_FILTERS[tab]:
        qs = base.filter(status=TAB_FILTERS[tab])
    else:
        qs = base

    counts = {
        'inbox': _inbox_for(request.user, base).count(),
        'pending_branch': base.filter(status=PendingAction.Status.PENDING_BRANCH).count(),
        'pending_gm': base.filter(status=PendingAction.Status.PENDING_GM).count(),
        'pending_officer': base.filter(status=PendingAction.Status.PENDING_OFFICER).count(),
        'returned': base.filter(status=PendingAction.Status.RETURNED).count(),
        'approved': base.filter(status=PendingAction.Status.APPROVED).count(),
        'mine': base.filter(requested_by=request.user).count(),
    }

    return render(request, 'pages/pending_actions/list.html', {
        'actions': qs.order_by('-requested_at')[:200],
        'tab': tab,
        'counts': counts,
        'is_gm': _is_general_manager(request.user),
        'is_hr_officer': _is_hr_officer(request.user),
        'is_branch_mgr': _is_branch_manager(request.user),
    })


@login_required
def pending_action_detail(request, action_id):
    action = get_object_or_404(
        PendingAction.objects.select_related(
            'employee', 'branch', 'requested_by',
            'branch_reviewed_by', 'gm_reviewed_by', 'assigned_officer', 'returned_by',
        ),
        id=action_id,
    )

    if not _user_visible_actions(request.user).filter(id=action.id).exists():
        messages.error(request, 'لا تملك صلاحية رؤية هذا الطلب.')
        return redirect('web:list_pending_actions')

    officers = []
    if _is_general_manager(request.user) and action.status == PendingAction.Status.PENDING_GM:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        officers = User.objects.filter(
            is_active=True,
            profile__role__role_type=Role.RoleType.HR_OFFICER,
        ).select_related('profile').order_by('first_name', 'username')

    current_stage = action.current_stage
    can_act = bool(current_stage) and _can_act_at_stage(request.user, action, current_stage)
    can_resubmit = (
        action.status == PendingAction.Status.RETURNED
        and (action.requested_by_id == request.user.id or request.user.is_superuser)
    )

    return render(request, 'pages/pending_actions/detail.html', {
        'action': action,
        'officers': officers,
        'can_act': can_act,
        'can_resubmit': can_resubmit,
        'current_stage': current_stage,
    })


# =============================================================================
# اتخاذ القرارات (POST)
# =============================================================================

def _locked(action_id):
    return PendingAction.objects.select_for_update().get(id=action_id)


@login_required
def branch_approve_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    notes = (request.POST.get('notes') or '').strip()
    try:
        with transaction.atomic():
            action = _locked(action_id)
            if not _can_act_at_stage(request.user, action, PendingAction.Stage.BRANCH):
                messages.error(request, 'لا تملك صلاحية الموافقة على هذا الطلب.')
                return redirect('web:list_pending_actions')
            from apps.core.services.pending_actions import branch_approve
            branch_approve(action, request.user, notes)
        messages.success(request, 'تمت موافقتك. الطلب الآن بانتظار المدير العام.')
    except Exception as e:
        messages.error(request, f'تعذّر التنفيذ: {e}')
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def gm_approve_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    notes = (request.POST.get('notes') or '').strip()
    officer_id = request.POST.get('officer_id')
    if not officer_id:
        messages.error(request, 'يجب اختيار موظف موارد للإسناد.')
        return redirect('web:pending_action_detail', action_id=action_id)

    try:
        with transaction.atomic():
            action = _locked(action_id)
            if not _can_act_at_stage(request.user, action, PendingAction.Stage.GM):
                messages.error(request, 'لا تملك صلاحية الموافقة كمدير عام.')
                return redirect('web:list_pending_actions')

            from django.contrib.auth import get_user_model
            User = get_user_model()
            officer = User.objects.filter(id=officer_id, is_active=True).first()
            if not officer:
                messages.error(request, 'موظف الموارد المختار غير موجود.')
                return redirect('web:pending_action_detail', action_id=action_id)

            from apps.core.services.pending_actions import gm_approve_and_assign
            gm_approve_and_assign(action, request.user, officer, notes)
        messages.success(request, 'تمت موافقتك. تم إسناد المهمة لموظف الموارد.')
    except Exception as e:
        messages.error(request, f'تعذّر التنفيذ: {e}')
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def officer_approve_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    notes = (request.POST.get('notes') or '').strip()
    try:
        with transaction.atomic():
            action = _locked(action_id)
            if not _can_act_at_stage(request.user, action, PendingAction.Stage.OFFICER):
                messages.error(request, 'لا تملك صلاحية تنفيذ هذا الطلب.')
                return redirect('web:list_pending_actions')
            from apps.core.services.pending_actions import officer_approve
            msg = officer_approve(action, request.user, notes)
        messages.success(request, f'تمت الموافقة وتنفيذ العملية: {msg}')
    except Exception as e:
        messages.error(request, f'فشل تنفيذ العملية: {e}')
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def return_pending_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    notes = (request.POST.get('notes') or '').strip()
    if not notes:
        messages.error(request, 'ملاحظات الإرجاع إجبارية.')
        return redirect('web:pending_action_detail', action_id=action_id)

    try:
        with transaction.atomic():
            action = _locked(action_id)
            stage = action.current_stage
            if not stage or not _can_act_at_stage(request.user, action, stage):
                messages.error(request, 'لا تملك صلاحية إرجاع هذا الطلب.')
                return redirect('web:list_pending_actions')
            from apps.core.services.pending_actions import return_action
            return_action(action, request.user, notes)
        messages.success(request, 'تم إرجاع الطلب لمقدّم الطلب للتعديل.')
    except Exception as e:
        messages.error(request, f'تعذّر التنفيذ: {e}')
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def resubmit_pending_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    try:
        with transaction.atomic():
            action = _locked(action_id)
            from apps.core.services.pending_actions import resubmit_action
            resubmit_action(action, request.user)
        messages.success(request, 'تم إعادة إرسال الطلب لمدير الفرع.')
    except Exception as e:
        messages.error(request, f'تعذّر التنفيذ: {e}')
    return redirect('web:pending_action_detail', action_id=action_id)


# =============================================================================
# توافق خلفي مع الأسماء القديمة (تُعيد التوجيه للجديد)
# =============================================================================

@login_required
def approve_pending_action(request, action_id):
    messages.info(request, 'تمّت ترقية نظام الموافقات. استخدم صفحة التفاصيل لاتخاذ القرار.')
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def reject_pending_action(request, action_id):
    messages.info(request, 'تمّت ترقية النظام. لإرجاع الطلب استخدم زر "إرجاع للتعديل".')
    return redirect('web:pending_action_detail', action_id=action_id)
