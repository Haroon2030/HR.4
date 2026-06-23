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
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.models import PendingAction, Role
from apps.core.services.approval_routing import first_stage_pending_q, resolve_first_approver, first_stage_tab_label
from apps.core.services.workflow_access import can_resubmit_operation, can_view_operations, can_delete_pending_action
from apps.core.web_views._helpers import (
    _can_act_at_stage,
    _can_return_at_stage,
    _is_branch_manager,
    _is_general_manager,
    _is_hr_officer,
)


def _user_display(user):
    if user is None:
        return '-'
    return (user.get_full_name() or user.username or '-').strip() or '-'


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


def _managed_scope_for_user(user) -> tuple[list[int], list[int]]:
    """فروع وإدارات يديرها المستخدم — مرة واحدة لكل طلب."""
    cached = getattr(user, '_hr_managed_scope', None)
    if cached is not None:
        return cached
    if user.is_superuser:
        cached = ([], [])
    else:
        cached = (
            list(user.managed_branches.filter(is_deleted=False).values_list('id', flat=True)),
            list(user.managed_administrations.filter(is_deleted=False).values_list('id', flat=True)),
        )
    user._hr_managed_scope = cached
    return cached


def _user_visible_actions(user):
    from apps.employees.services.cash_shortage_access import (
        branch_accountant_branch_ids,
        is_branch_accountant,
    )

    qs = PendingAction.objects.select_related(
        'employee', 'branch', 'administration', 'requested_by',
        'branch_reviewed_by', 'gm_reviewed_by', 'assigned_officer', 'returned_by',
    )
    if user.is_superuser or _is_general_manager(user):
        return qs

    if is_branch_accountant(user):
        ba_ids = list(branch_accountant_branch_ids(user))
        filters = Q(requested_by=user)
        if ba_ids:
            filters |= Q(
                action_type=PendingAction.ActionType.CASH_SHORTAGE,
                branch_id__in=ba_ids,
            )
        return qs.filter(filters).distinct()

    filters = Q(requested_by=user)
    managed_ids, managed_admin_ids = _managed_scope_for_user(user)
    if managed_ids:
        filters |= Q(branch_id__in=managed_ids)
    if managed_admin_ids:
        filters |= Q(administration_id__in=managed_admin_ids)
    if _is_hr_officer(user):
        filters |= Q(assigned_officer=user)
    return qs.filter(filters).distinct()


def _inbox_for(user, qs):
    f = Q()
    has_filter = False
    if user.is_superuser or _is_general_manager(user):
        f |= Q(status=PendingAction.Status.PENDING_GM)
        has_filter = True
    first_q = first_stage_pending_q(user, model_status_pending_branch=PendingAction.Status.PENDING_BRANCH)
    if first_q.children:
        f |= first_q
        has_filter = True
    if _is_hr_officer(user) or user.is_superuser:
        f |= Q(status=PendingAction.Status.PENDING_OFFICER, assigned_officer=user) \
            if not user.is_superuser \
            else Q(status=PendingAction.Status.PENDING_OFFICER)
        has_filter = True
    f |= Q(status=PendingAction.Status.RETURNED, requested_by=user)
    return qs.filter(f) if has_filter else qs.none()


# =============================================================================
# Unified Inbox Adapter — يدمج PendingAction + EmploymentRequest في عرض موحّد
# =============================================================================

# مَخطّط الحالات بين النموذجين (متطابقة فعلياً):
#   pending_branch / pending_gm / pending_officer / approved / returned (PendingAction)
#   pending_branch / pending_gm / pending_officer / approved / rejected (EmploymentRequest)
# نعرضها بنفس البُنية في الـ template.

def _user_visible_hire_requests(user):
    """طلبات التوظيف المرئية للمستخدم بنفس منطق _user_visible_actions."""
    from apps.employees.models import EmploymentRequest

    qs = EmploymentRequest.objects.select_related(
        'branch', 'administration', 'requested_by', 'branch_reviewed_by',
        'gm_reviewed_by', 'assigned_officer',
    )
    if user.is_superuser or _is_general_manager(user):
        return qs

    filters = Q(requested_by=user)
    managed_ids, managed_admin_ids = _managed_scope_for_user(user)
    if managed_ids:
        filters |= Q(branch_id__in=managed_ids)
    if managed_admin_ids:
        filters |= Q(administration_id__in=managed_admin_ids)
    if _is_hr_officer(user):
        filters |= Q(assigned_officer=user)
    return qs.filter(filters).distinct()


def _inbox_for_hire(user, qs):
    """فلترة طلبات التوظيف المنتظِرة إجراءً من المستخدم."""
    from apps.employees.models import EmploymentRequest

    f = Q()
    has_filter = False
    if user.is_superuser or _is_general_manager(user):
        f |= Q(status=EmploymentRequest.Status.PENDING_GM)
        has_filter = True
    first_q = first_stage_pending_q(user, model_status_pending_branch=EmploymentRequest.Status.PENDING_BRANCH)
    if first_q.children:
        f |= first_q
        has_filter = True
    if _is_hr_officer(user) or user.is_superuser:
        f |= (
            Q(status=EmploymentRequest.Status.PENDING_OFFICER, assigned_officer=user)
            if not user.is_superuser
            else Q(status=EmploymentRequest.Status.PENDING_OFFICER)
        )
        has_filter = True
    return qs.filter(f) if has_filter else qs.none()


def _wrap_action(a, user):
    """تحويل PendingAction إلى DTO موحّد للعرض."""
    first = resolve_first_approver(a)
    can_del = can_delete_pending_action(user, a)
    if a.status == PendingAction.Status.APPROVED:
        delete_confirm = (
            f'إخفاء الطلب المكتمل #{a.id} ({a.get_action_type_display()}) من القائمة؟ '
            'العملية نُفّذت ولا يُلغى تنفيذها.'
        )
    else:
        delete_confirm = f'حذف الطلب #{a.id} ({a.get_action_type_display()})؟ لا يمكن التراجع.'
    return SimpleNamespace(
        kind='action',
        id=a.id,
        action_type=a.action_type,
        action_type_display=a.get_action_type_display(),
        employee_name=a.employee.name if a.employee_id else '-',
        branch_name=a.branch.name if a.branch_id else '-',
        administration_name=a.administration.name if a.administration_id else '-',
        first_stage_label=first.stage_label,
        status=a.status,
        status_display=a.get_status_display(),
        branch_reviewed_at=a.branch_reviewed_at,
        gm_reviewed_at=a.gm_reviewed_at,
        officer_reviewed_at=a.officer_reviewed_at,
        assigned_officer=a.assigned_officer,
        requested_by=a.requested_by,
        requested_by_name=_user_display(a.requested_by),
        requested_at=a.requested_at,
        updated_at=a.updated_at,
        resubmit_count=a.resubmit_count or 0,
        detail_url=reverse('web:pending_action_detail', args=[a.id]),
        delete_url=reverse('web:delete_pending_action', args=[a.id]) if can_del else '',
        delete_confirm=delete_confirm,
    )


def _wrap_hire(r, user):
    """تحويل EmploymentRequest إلى DTO موحّد للعرض."""
    from apps.core.services.workflow_access import can_delete_employment_request

    first = resolve_first_approver(r)
    can_del = can_delete_employment_request(user, r)
    from apps.employees.models import EmploymentRequest
    if r.status == EmploymentRequest.Status.APPROVED:
        delete_confirm = (
            f'إخفاء طلب التوظيف المكتمل «{r.name}» من القائمة؟ '
            'تم اعتماد الطلب ولا يُلغى إنشاء الموظف.'
        )
    else:
        delete_confirm = f'حذف طلب التوظيف «{r.name}»؟ لا يمكن التراجع.'
    return SimpleNamespace(
        kind='hire',
        id=r.id,
        action_type='hire',
        action_type_display='توظيف جديد',
        employee_name=r.name,
        branch_name=r.branch.name if r.branch_id else '-',
        administration_name=r.administration.name if r.administration_id else '-',
        first_stage_label=first.stage_label,
        status=r.status,
        status_display=r.get_status_display(),
        branch_reviewed_at=r.branch_reviewed_at,
        gm_reviewed_at=r.gm_reviewed_at,
        officer_reviewed_at=r.officer_reviewed_at,
        assigned_officer=r.assigned_officer,
        requested_by=r.requested_by,
        requested_by_name=_user_display(r.requested_by),
        requested_at=r.created_at,
        updated_at=r.updated_at,
        resubmit_count=0,
        detail_url=reverse('web:list_employment_requests'),
        delete_url=reverse('web:delete_employment_request', args=[r.id]) if can_del else '',
        delete_confirm=delete_confirm,
    )


@login_required
def list_pending_actions(request):
    from apps.employees.models import EmploymentRequest

    if not can_view_operations(request.user):
        messages.error(request, 'لا تملك صلاحية عرض طلبات العمليات.')
        return redirect('web:dashboard')

    tab = request.GET.get('tab', 'inbox')
    base = _user_visible_actions(request.user)
    base_hire = _user_visible_hire_requests(request.user)

    # ─ فلترة كل نموذج حسب التبويب ────────────────────────────────
    if tab == 'inbox':
        qs = _inbox_for(request.user, base)
        qs_hire = _inbox_for_hire(request.user, base_hire)
    elif tab == 'mine':
        qs = base.filter(requested_by=request.user)
        qs_hire = base_hire.filter(requested_by=request.user)
    elif tab == 'pending_branch':
        qs = base.filter(status=PendingAction.Status.PENDING_BRANCH)
        qs_hire = base_hire.filter(status=EmploymentRequest.Status.PENDING_BRANCH)
    elif tab == 'pending_gm':
        qs = base.filter(status=PendingAction.Status.PENDING_GM)
        qs_hire = base_hire.filter(status=EmploymentRequest.Status.PENDING_GM)
    elif tab == 'pending_officer':
        qs = base.filter(status=PendingAction.Status.PENDING_OFFICER)
        qs_hire = base_hire.filter(status=EmploymentRequest.Status.PENDING_OFFICER)
    elif tab == 'returned':
        qs = base.filter(status=PendingAction.Status.RETURNED)
        qs_hire = base_hire.none()  # EmploymentRequest ليس له حالة "مرتجع"
    elif tab == 'approved':
        qs = base.filter(status=PendingAction.Status.APPROVED)
        qs_hire = base_hire.filter(status=EmploymentRequest.Status.APPROVED)
    else:
        qs = base
        qs_hire = base_hire

    # ─ دمج وفرز موحّد (حد أقصى لتقليل استهلاك الذاكرة) ─────────
    _MERGE_LIMIT = 200
    rows = [_wrap_action(a, request.user) for a in qs.order_by('-requested_at')[:_MERGE_LIMIT]]
    rows += [_wrap_hire(r, request.user) for r in qs_hire.order_by('-created_at')[:_MERGE_LIMIT]]
    rows_may_be_truncated = len(rows) >= _MERGE_LIMIT
    rows.sort(key=lambda x: x.updated_at or x.requested_at, reverse=True)

    # ─ بحث ذكي عبر الحقول ────────────────────────────────────────
    q = (request.GET.get('q') or '').strip()
    if q:
        ql = q.lower()
        def _match(r):
            blobs = [
                getattr(r, 'employee_name', '') or '',
                getattr(r, 'branch_name', '') or '',
                getattr(r, 'action_type_display', '') or '',
                getattr(r, 'status_display', '') or '',
                str(getattr(r, 'id', '') or ''),
            ]
            rb = getattr(r, 'requested_by', None)
            if rb:
                blobs.append(getattr(rb, 'get_full_name', lambda: '')() or getattr(rb, 'username', '') or '')
            return any(ql in str(b).lower() for b in blobs)
        rows = [r for r in rows if _match(r)]

    total_rows = len(rows)

    # ─ ترقيم: 10 صفوف/صفحة ───────────────────────────────────────
    from django.core.paginator import Paginator
    paginator = Paginator(rows, 10)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    # ─ العدّادات الموحّدة (aggregate لتقليل الاستعلامات) ────────
    from django.db.models import Count, Case, When, IntegerField
    pa_agg = base.aggregate(
        c_branch=Count('id', filter=Q(status=PendingAction.Status.PENDING_BRANCH)),
        c_gm=Count('id', filter=Q(status=PendingAction.Status.PENDING_GM)),
        c_officer=Count('id', filter=Q(status=PendingAction.Status.PENDING_OFFICER)),
        c_returned=Count('id', filter=Q(status=PendingAction.Status.RETURNED)),
        c_approved=Count('id', filter=Q(status=PendingAction.Status.APPROVED)),
        c_mine=Count('id', filter=Q(requested_by=request.user)),
    )
    hr_agg = base_hire.aggregate(
        c_branch=Count('id', filter=Q(status=EmploymentRequest.Status.PENDING_BRANCH)),
        c_gm=Count('id', filter=Q(status=EmploymentRequest.Status.PENDING_GM)),
        c_officer=Count('id', filter=Q(status=EmploymentRequest.Status.PENDING_OFFICER)),
        c_approved=Count('id', filter=Q(status=EmploymentRequest.Status.APPROVED)),
        c_mine=Count('id', filter=Q(requested_by=request.user)),
    )
    from apps.core.services.sidebar_counts import get_sidebar_counts

    counts = {
        'inbox': get_sidebar_counts(request.user)['pending_for_me_count'],
        'pending_branch': pa_agg['c_branch'] + hr_agg['c_branch'],
        'pending_gm': pa_agg['c_gm'] + hr_agg['c_gm'],
        'pending_officer': pa_agg['c_officer'] + hr_agg['c_officer'],
        'returned': pa_agg['c_returned'],
        'approved': pa_agg['c_approved'] + hr_agg['c_approved'],
        'mine': pa_agg['c_mine'] + hr_agg['c_mine'],
    }

    return render(request, 'pages/pending_actions/list.html', {
        'actions': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'total_rows': total_rows,
        'query': q,
        'tab': tab,
        'counts': counts,
        'is_gm': _is_general_manager(request.user),
        'is_hr_officer': _is_hr_officer(request.user),
        'is_branch_mgr': _is_branch_manager(request.user),
        'resolve_first_approver': resolve_first_approver,
        'first_stage_tab_label': first_stage_tab_label(request.user),
        'rows_may_be_truncated': rows_may_be_truncated,
    })


@login_required
def pending_action_detail(request, action_id):
    if not can_view_operations(request.user):
        messages.error(request, 'لا تملك صلاحية عرض طلبات العمليات.')
        return redirect('web:dashboard')
    action = get_object_or_404(
        PendingAction.objects.select_related(
            'employee', 'branch', 'administration', 'requested_by',
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
        and can_resubmit_operation(request.user)
    )

    return render(request, 'pages/pending_actions/detail.html', {
        'action': action,
        'officers': officers,
        'can_act': can_act,
        'can_resubmit': can_resubmit,
        'current_stage': current_stage,
        'first_decision': resolve_first_approver(action),
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
        if action.action_type == PendingAction.ActionType.CASH_SHORTAGE:
            messages.success(request, 'تم اعتماد عجز الكاشير وتنفيذه.')
        else:
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
            if not stage or not _can_return_at_stage(request.user, action, stage):
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


@login_required
def delete_pending_action(request, action_id):
    """حذف ناعم لطلب عملية غير مُنفَّذ."""
    if not can_view_operations(request.user):
        messages.error(request, 'لا تملك صلاحية عرض طلبات العمليات.')
        return redirect('web:dashboard')

    if request.method != 'POST':
        return redirect('web:list_pending_actions')

    action = get_object_or_404(_user_visible_actions(request.user), id=action_id)
    if not can_delete_pending_action(request.user, action):
        messages.error(request, 'لا تملك صلاحية حذف هذا الطلب.')
        return redirect('web:list_pending_actions')

    label = f'#{action.id} — {action.get_action_type_display()}'
    from apps.core.services.pending_actions import revert_employee_settlement_pending_status
    revert_employee_settlement_pending_status(action)
    action.delete()
    messages.success(request, f'تم حذف الطلب {label}.')
    return redirect('web:list_pending_actions')
