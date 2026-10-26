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
from apps.core.services.approval_routing import managed_branch_ids, first_stage_pending_q, resolve_first_approver, first_stage_tab_label
from apps.core.services.workflow_access import can_resubmit_operation, can_view_operations, can_delete_pending_action
from apps.core.services.pending_actions import is_settlement_final_stage
from apps.core.utils.user_errors import log_web_action_error
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

# كل ما يُعدّ «قيد المراجعة» (لم يُعتمد ولم يُرتجع ولم يُرفض)
OPEN_ACTION_STATUSES = (
    PendingAction.Status.PENDING_BRANCH,
    PendingAction.Status.PENDING_GM,
    PendingAction.Status.PENDING_OFFICER,
    PendingAction.Status.PENDING_ACCOUNTANT,
)
OPEN_HIRE_STATUSES = ('pending', 'pending_branch', 'pending_gm', 'pending_officer')

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
            managed_branch_ids(user),
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
        'employee', 'employee__department', 'branch', 'administration', 'requested_by',
        'branch_reviewed_by', 'gm_reviewed_by', 'assigned_officer', 'returned_by',
    )
    # مدير الموارد (المدير العام) يرى كل الطلبات المرفوعة، تابعة لإدارة أو غير مرتبطة.
    if user.is_superuser or _is_general_manager(user):
        return qs

    if is_branch_accountant(user):
        ba_ids = list(branch_accountant_branch_ids(user))
        filters = Q(requested_by=user) | Q(status=PendingAction.Status.PENDING_ACCOUNTANT)
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
    from apps.employees.services.cash_shortage_access import is_branch_accountant

    f = Q()
    has_filter = False
    if user.is_superuser or _is_general_manager(user):
        # مدير الموارد: كل الطلبات غير المنتهية في أي مرحلة (بلا استثناء)
        f |= Q(status__in=[
            PendingAction.Status.PENDING_BRANCH,
            PendingAction.Status.PENDING_GM,
            PendingAction.Status.PENDING_OFFICER,
            PendingAction.Status.PENDING_ACCOUNTANT,
        ])
        has_filter = True
    first_q = first_stage_pending_q(
        user, model=PendingAction, model_status_pending_branch=PendingAction.Status.PENDING_BRANCH,
    )
    if first_q.children:
        f |= first_q
        has_filter = True
    if _is_general_manager(user):
        f |= Q(status=PendingAction.Status.PENDING_OFFICER)
        has_filter = True
    elif _is_hr_officer(user):
        f |= Q(status=PendingAction.Status.PENDING_OFFICER, assigned_officer=user)
        has_filter = True
    if _is_general_manager(user) or is_branch_accountant(user):
        f |= Q(status=PendingAction.Status.PENDING_ACCOUNTANT)
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
    """طلبات التوظيف المرئية للمستخدم — نفس قاعدة قائمة طلبات التوظيف وصفحة تفاصيلها."""
    from apps.core.web_views.employment_requests import _hire_visibility_q
    from apps.employees.models import EmploymentRequest

    qs = EmploymentRequest.objects.select_related(
        'branch', 'department', 'administration', 'requested_by', 'branch_reviewed_by',
        'gm_reviewed_by', 'assigned_officer',
    )
    visible = _hire_visibility_q(user)
    if visible is None:
        return qs
    return qs.filter(visible).distinct()


def _inbox_for_hire(user, qs):
    """فلترة طلبات التوظيف المنتظِرة إجراءً من المستخدم."""
    from apps.employees.models import EmploymentRequest

    f = Q()
    has_filter = False
    if user.is_superuser or _is_general_manager(user):
        f |= Q(status__in=[
            EmploymentRequest.Status.PENDING,
            EmploymentRequest.Status.PENDING_BRANCH,
            EmploymentRequest.Status.PENDING_GM,
            EmploymentRequest.Status.PENDING_OFFICER,
        ])
        has_filter = True
    first_q = first_stage_pending_q(
        user, model=EmploymentRequest, model_status_pending_branch=EmploymentRequest.Status.PENDING_BRANCH,
    )
    if first_q.children:
        f |= first_q
        has_filter = True
    if _is_general_manager(user):
        f |= Q(status=EmploymentRequest.Status.PENDING_OFFICER)
        has_filter = True
    elif _is_hr_officer(user):
        f |= Q(status=EmploymentRequest.Status.PENDING_OFFICER, assigned_officer=user)
        has_filter = True
    # الطلب المُرتجَع ينتظر مقدّمه ليعدّله ويعيد إرساله
    f |= Q(status=EmploymentRequest.Status.RETURNED, requested_by=user)
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
        department_name=a.employee.department.name if a.employee_id and a.employee.department_id else '-',
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
        can_act=bool(a.current_stage) and _can_act_at_stage(user, a, a.current_stage),
        act_url=reverse('web:pending_action_detail', args=[a.id]) + '?panel=approve',
        delete_url=reverse('web:delete_pending_action', args=[a.id]) if can_del else '',
        delete_confirm=delete_confirm,
    )


def _can_act_on_hire(user, r) -> bool:
    """هل للمستخدم إجراء متاح الآن على طلب التوظيف (حسب مرحلته)؟"""
    from apps.core.services.workflow_access import (
        can_first_approve_employment_request,
        can_gm_approve_employment_request,
        can_officer_act_employment_request,
    )
    from apps.employees.models import EmploymentRequest

    awaiting_requester = (
        r.status == EmploymentRequest.Status.RETURNED
        and (r.requested_by_id == user.id or user.is_superuser)
    )
    return bool(
        awaiting_requester
        or can_first_approve_employment_request(user, r)
        or can_gm_approve_employment_request(user, r)
        or can_officer_act_employment_request(user, r)
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
        department_name=r.department.name if r.department_id else '-',
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
        detail_url=reverse('web:employment_request_detail', args=[r.id]),
        can_act=_can_act_on_hire(user, r),
        act_url=reverse('web:employment_request_detail', args=[r.id]) + '#decision-card',
        delete_url=reverse('web:delete_employment_request', args=[r.id]) if can_del else '',
        delete_confirm=delete_confirm,
    )


def _pending_list_filters(request) -> dict:
    """قراءة قيم الفلترة من الرابط (القيم غير الصالحة تُتجاهل)."""
    from datetime import date

    def _date(raw):
        try:
            return date.fromisoformat((raw or '').strip()[:10]) if raw else None
        except ValueError:
            return None

    valid_types = {'hire', *PendingAction.ActionType.values}
    type_ = (request.GET.get('type') or '').strip()
    branch = (request.GET.get('branch') or '').strip()
    date_from = _date(request.GET.get('date_from'))
    date_to = _date(request.GET.get('date_to'))
    return {
        'type': type_ if type_ in valid_types else '',
        'branch': branch if branch.isdigit() else '',
        'date_from': date_from,
        'date_to': date_to,
        'date_from_raw': date_from.isoformat() if date_from else '',
        'date_to_raw': date_to.isoformat() if date_to else '',
    }


def _apply_pending_list_filters(qs, qs_hire, filters):
    """طلبات العمليات + طلبات التوظيف بنفس الفلاتر."""
    if filters['type'] == 'hire':
        qs = qs.none()
    elif filters['type']:
        qs = qs.filter(action_type=filters['type'])
        qs_hire = qs_hire.none()
    if filters['branch']:
        qs = qs.filter(branch_id=int(filters['branch']))
        qs_hire = qs_hire.filter(branch_id=int(filters['branch']))
    if filters['date_from']:
        qs = qs.filter(requested_at__date__gte=filters['date_from'])
        qs_hire = qs_hire.filter(created_at__date__gte=filters['date_from'])
    if filters['date_to']:
        qs = qs.filter(requested_at__date__lte=filters['date_to'])
        qs_hire = qs_hire.filter(created_at__date__lte=filters['date_to'])
    return qs, qs_hire


def _filter_branch_choices(user):
    """الفروع المتاحة للمستخدم فقط في قائمة الفلترة."""
    from apps.core.models import Branch
    from apps.core.services.access_control import filter_branches_queryset

    return list(
        filter_branches_queryset(user, Branch.objects.filter(is_active=True, is_deleted=False))
        .order_by('name').values_list('id', 'name')
    )


@login_required
def list_pending_actions(request):
    from apps.employees.models import EmploymentRequest

    if not can_view_operations(request.user):
        messages.error(request, 'لا تملك صلاحية عرض طلبات العمليات.')
        return redirect('web:dashboard')

    tab = request.GET.get('tab', 'review')
    base = _user_visible_actions(request.user)
    base_hire = _user_visible_hire_requests(request.user)

    # ─ فلترة كل نموذج حسب التبويب ────────────────────────────────
    if tab == 'review':
        # كل ما قيد المراجعة (بغضّ النظر عن صاحب الدور الحالي)
        qs = base.filter(status__in=OPEN_ACTION_STATUSES)
        qs_hire = base_hire.filter(status__in=OPEN_HIRE_STATUSES)
    elif tab == 'inbox':
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
    elif tab == 'rejected':
        qs = base.none()  # الإجراءات السريعة لا رفض نهائي لها (تُرتجع)
        qs_hire = base_hire.filter(status=EmploymentRequest.Status.REJECTED)
    elif tab == 'returned':
        qs = base.filter(status=PendingAction.Status.RETURNED)
        qs_hire = base_hire.filter(status=EmploymentRequest.Status.RETURNED)
    elif tab == 'approved':
        qs = base.filter(status=PendingAction.Status.APPROVED)
        qs_hire = base_hire.filter(status=EmploymentRequest.Status.APPROVED)
    else:
        qs = base
        qs_hire = base_hire

    # ─ الفلترة: نوع الطلب، الفرع، فترة تاريخ الطلب (على مستوى قاعدة البيانات) ─
    filters = _pending_list_filters(request)
    qs, qs_hire = _apply_pending_list_filters(qs, qs_hire, filters)

    # ─ دمج وفرز موحّد بلا أي حد أقصى: لا يُخفى أي طلب عن المستخدم ─────
    # الفرز والترقيم على مفاتيح خفيفة (id + تاريخ) ثم تُحمَّل صفوف الصفحة فقط.
    # البحث النصي يحتاج بيانات كل صف فيُحمَّل الكل في هذه الحالة.
    q = (request.GET.get('q') or '').strip()

    def _wrap_rows(pa_ids, hire_ids):
        pa_map = {a.id: a for a in qs.filter(id__in=pa_ids)}
        hire_map = {r.id: r for r in qs_hire.filter(id__in=hire_ids)}
        return pa_map, hire_map

    if q:
        ql = q.lower()
        rows = [_wrap_action(a, request.user) for a in qs]
        rows += [_wrap_hire(r, request.user) for r in qs_hire]
        rows.sort(key=lambda x: x.updated_at or x.requested_at, reverse=True)

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
        from django.core.paginator import Paginator
        paginator = Paginator(rows, 10)
        page_obj = paginator.get_page(request.GET.get('page') or 1)
        page_rows = list(page_obj.object_list)
    else:
        keys = [
            (updated or requested, 'action', pk)
            for pk, updated, requested in qs.values_list('id', 'updated_at', 'requested_at')
        ]
        keys += [
            (updated or created, 'hire', pk)
            for pk, updated, created in qs_hire.values_list('id', 'updated_at', 'created_at')
        ]
        keys.sort(key=lambda k: (k[0] is not None, k[0]), reverse=True)
        total_rows = len(keys)
        from django.core.paginator import Paginator
        paginator = Paginator(keys, 10)
        page_obj = paginator.get_page(request.GET.get('page') or 1)
        page_keys = list(page_obj.object_list)
        pa_map, hire_map = _wrap_rows(
            [pk for _, kind, pk in page_keys if kind == 'action'],
            [pk for _, kind, pk in page_keys if kind == 'hire'],
        )
        page_rows = []
        for _, kind, pk in page_keys:
            if kind == 'action' and pk in pa_map:
                page_rows.append(_wrap_action(pa_map[pk], request.user))
            elif kind == 'hire' and pk in hire_map:
                page_rows.append(_wrap_hire(hire_map[pk], request.user))

    # ─ العدّادات الموحّدة (aggregate لتقليل الاستعلامات) ────────
    from django.db.models import Count
    pa_agg = base.aggregate(
        c_branch=Count('id', filter=Q(status=PendingAction.Status.PENDING_BRANCH)),
        c_gm=Count('id', filter=Q(status=PendingAction.Status.PENDING_GM)),
        c_officer=Count('id', filter=Q(status=PendingAction.Status.PENDING_OFFICER)),
        c_open=Count('id', filter=Q(status__in=OPEN_ACTION_STATUSES)),
        c_returned=Count('id', filter=Q(status=PendingAction.Status.RETURNED)),
        c_approved=Count('id', filter=Q(status=PendingAction.Status.APPROVED)),
        c_mine=Count('id', filter=Q(requested_by=request.user)),
    )
    hr_agg = base_hire.aggregate(
        c_branch=Count('id', filter=Q(status=EmploymentRequest.Status.PENDING_BRANCH)),
        c_gm=Count('id', filter=Q(status=EmploymentRequest.Status.PENDING_GM)),
        c_officer=Count('id', filter=Q(status=EmploymentRequest.Status.PENDING_OFFICER)),
        c_open=Count('id', filter=Q(status__in=OPEN_HIRE_STATUSES)),
        c_approved=Count('id', filter=Q(status=EmploymentRequest.Status.APPROVED)),
        c_rejected=Count('id', filter=Q(status=EmploymentRequest.Status.REJECTED)),
        c_returned=Count('id', filter=Q(status=EmploymentRequest.Status.RETURNED)),
        c_mine=Count('id', filter=Q(requested_by=request.user)),
    )
    from apps.core.services.sidebar_counts import get_sidebar_counts

    counts = {
        'review': pa_agg['c_open'] + hr_agg['c_open'],
        'inbox': get_sidebar_counts(request.user)['pending_for_me_count'],
        'pending_branch': pa_agg['c_branch'] + hr_agg['c_branch'],
        'pending_gm': pa_agg['c_gm'] + hr_agg['c_gm'],
        'pending_officer': pa_agg['c_officer'] + hr_agg['c_officer'],
        'returned': pa_agg['c_returned'] + hr_agg['c_returned'],
        'rejected': hr_agg['c_rejected'],
        'approved': pa_agg['c_approved'] + hr_agg['c_approved'],
        'mine': pa_agg['c_mine'] + hr_agg['c_mine'],
    }

    from urllib.parse import urlencode
    filter_qs = urlencode({
        k: v for k, v in (
            ('tab', tab), ('q', q), ('type', filters['type']), ('branch', filters['branch']),
            ('date_from', filters['date_from_raw']), ('date_to', filters['date_to_raw']),
        ) if v
    })

    return render(request, 'pages/pending_actions/list.html', {
        'actions': page_rows,
        'filters': filters,
        'filters_active': any(filters[k] for k in ('type', 'branch', 'date_from_raw', 'date_to_raw')),
        'filter_qs': filter_qs,
        'type_choices': [('hire', 'توظيف جديد'), *PendingAction.ActionType.choices],
        'filter_branches': _filter_branch_choices(request.user),
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
    if (_is_general_manager(request.user) and action.status == PendingAction.Status.PENDING_GM
            and not action.executed_at):
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

    from apps.core.services.pending_actions import SETTLEMENT_PENDING_ACTION_TYPES
    settlement = None
    if (
        can_act and current_stage == PendingAction.Stage.OFFICER
        and action.action_type in SETTLEMENT_PENDING_ACTION_TYPES
        and not action.executed_at
    ):
        settlement = settlement_panel_context(action)

    # ?panel=approve|return يفتح كتلة القرار مباشرة (من زر «اعتماد» في القائمة)
    auto_panel = request.GET.get('panel')
    if auto_panel not in ('approve', 'return') or not can_act:
        auto_panel = None
    elif settlement and not settlement['signed_url']:
        auto_panel = None  # التصفية تحتاج الملف الموقّع أولاً

    return render(request, 'pages/pending_actions/detail.html', {
        'action': action,
        'auto_panel': auto_panel,
        'settlement': settlement,
        'officers': officers,
        'can_act': can_act,
        'can_resubmit': can_resubmit,
        'current_stage': current_stage,
        'first_decision': resolve_first_approver(action),
        'is_final_stage': is_settlement_final_stage(action),
        'accountant_stage': current_stage == PendingAction.Stage.ACCOUNTANT,
    })


# =============================================================================
# اتخاذ القرارات (POST)
# =============================================================================

def _locked(action_id):
    return PendingAction.objects.select_for_update().get(id=action_id)


def _deny_if_action_not_visible(request, action):
    if _user_visible_actions(request.user).filter(pk=action.pk).exists():
        return False
    messages.error(request, 'لا تملك صلاحية رؤية هذا الطلب.')
    return True


@login_required
def branch_approve_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    notes = (request.POST.get('notes') or '').strip()
    try:
        with transaction.atomic():
            action = _locked(action_id)
            if _deny_if_action_not_visible(request, action):
                return redirect('web:list_pending_actions')
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
        messages.error(request, log_web_action_error('branch_approve_action', e))
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
            if _deny_if_action_not_visible(request, action):
                return redirect('web:list_pending_actions')
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
        messages.error(request, log_web_action_error('branch_approve_action', e))
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def gm_final_approve_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    notes = (request.POST.get('notes') or '').strip()
    try:
        with transaction.atomic():
            action = _locked(action_id)
            if _deny_if_action_not_visible(request, action):
                return redirect('web:list_pending_actions')
            if not _can_act_at_stage(request.user, action, PendingAction.Stage.GM):
                messages.error(request, 'لا تملك صلاحية الاعتماد النهائي.')
                return redirect('web:list_pending_actions')
            from apps.core.services.pending_actions import gm_final_approve
            gm_final_approve(action, request.user, notes)
        messages.success(request, 'تم الاعتماد النهائي للتصفية.')
    except Exception as e:
        messages.error(request, log_web_action_error('gm_final_approve_action', e))
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def accountant_approve_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    notes = (request.POST.get('notes') or '').strip()
    try:
        with transaction.atomic():
            action = _locked(action_id)
            if _deny_if_action_not_visible(request, action):
                return redirect('web:list_pending_actions')
            if not _can_act_at_stage(request.user, action, PendingAction.Stage.ACCOUNTANT):
                messages.error(request, 'لا تملك صلاحية اعتماد المحاسب.')
                return redirect('web:list_pending_actions')
            from apps.core.services.pending_actions import accountant_approve
            accountant_approve(action, request.user, notes)
        messages.success(request, 'تم اعتماد المحاسب. الطلب الآن بانتظار الاعتماد النهائي لمدير الموارد.')
    except Exception as e:
        messages.error(request, log_web_action_error('accountant_approve_action', e))
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def officer_approve_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    notes = (request.POST.get('notes') or '').strip()
    try:
        with transaction.atomic():
            action = _locked(action_id)
            if _deny_if_action_not_visible(request, action):
                return redirect('web:list_pending_actions')
            if not _can_act_at_stage(request.user, action, PendingAction.Stage.OFFICER):
                messages.error(request, 'لا تملك صلاحية تنفيذ هذا الطلب.')
                return redirect('web:list_pending_actions')
            from apps.core.services.pending_actions import officer_approve
            msg = officer_approve(action, request.user, notes)
        messages.success(request, f'تمت الموافقة وتنفيذ العملية: {msg}')
    except Exception as e:
        messages.error(request, log_web_action_error('officer_approve_action', e))
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
            if _deny_if_action_not_visible(request, action):
                return redirect('web:list_pending_actions')
            stage = action.current_stage
            if not stage or not _can_return_at_stage(request.user, action, stage):
                messages.error(request, 'لا تملك صلاحية إرجاع هذا الطلب.')
                return redirect('web:list_pending_actions')
            from apps.core.services.pending_actions import return_action
            return_action(action, request.user, notes)
        messages.success(request, 'تم إرجاع الطلب لمقدّم الطلب للتعديل.')
    except Exception as e:
        messages.error(request, log_web_action_error('branch_approve_action', e))
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def resubmit_pending_action(request, action_id):
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    try:
        with transaction.atomic():
            action = _locked(action_id)
            if _deny_if_action_not_visible(request, action):
                return redirect('web:list_pending_actions')
            from apps.core.services.pending_actions import resubmit_action
            resubmit_action(action, request.user)
        messages.success(request, 'تم إعادة إرسال الطلب لمدير الفرع.')
    except Exception as e:
        messages.error(request, log_web_action_error('branch_approve_action', e))
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


# =============================================================================
# تعديل التصفية قبل الموافقة النهائية + رفع الملف الموقّع
# =============================================================================

def _settlement_end_date(action):
    from datetime import date as _date
    raw = (action.payload or {}).get('end_date')
    try:
        return _date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _settlement_base_financials(action):
    """البنود المحسوبة تلقائياً (قبل أي تعديل) — None إن تعذّر تحديد تاريخ التصفية."""
    from apps.employees.services.settlement_financials import compute_settlement_financials
    end_date = _settlement_end_date(action)
    if end_date is None:
        return None
    return compute_settlement_financials(action.employee, end_date)


def settlement_panel_context(action):
    """بيانات لوحة «تعديل التصفية» في صفحة الطلب."""
    from apps.employees.services.settlement_override import (
        DEDUCTION_FIELDS, MANUAL_KINDS, apply_override_to_financials, get_override,
    )
    base = _settlement_base_financials(action)
    override = get_override(action.payload)
    rows = []
    if base is not None:
        current = apply_override_to_financials(base, override)
        for field, label in DEDUCTION_FIELDS:
            rows.append({
                'field': field,
                'label': label,
                'value': current.get(field) or 0,
                'auto': base.get(field) or 0,
                'edited': field in override,
            })
    signed = action.signed_settlement
    return {
        'rows': rows,
        'manual_items': list(override.get('manual_items') or []),
        'manual_kinds': MANUAL_KINDS,
        'reason': override.get('reason', ''),
        'edited_by': override.get('edited_by', ''),
        'edited_at': override.get('edited_at', ''),
        'has_override': bool(override),
        'signed_url': signed.url if signed else '',
        'signed_name': signed.name.rsplit('/', 1)[-1] if signed else '',
        'preview_url': (
            reverse('web:hr_form_print', args=['final_settlement', action.employee_id])
            + f'?action={action.id}'
        ),
    }


def _settlement_guard(request, action_id):
    """يقفل الطلب ويتحقق أن المستخدم هو موظف الموارد المخوّل وأن الطلب تصفية قيد المراجعة."""
    from apps.core.services.pending_actions import SETTLEMENT_PENDING_ACTION_TYPES
    action = _locked(action_id)
    if _deny_if_action_not_visible(request, action):
        return action, redirect('web:list_pending_actions')
    if not _can_act_at_stage(request.user, action, PendingAction.Stage.OFFICER):
        messages.error(request, 'لا تملك صلاحية تعديل هذا الطلب.')
        return action, redirect('web:list_pending_actions')
    if action.action_type not in SETTLEMENT_PENDING_ACTION_TYPES:
        messages.error(request, 'هذا الإجراء متاح لطلبات التصفية فقط.')
        return action, redirect('web:pending_action_detail', action_id=action_id)
    if action.status != PendingAction.Status.PENDING_OFFICER or action.executed_at:
        messages.error(request, 'لا يمكن تعديل التصفية بعد تنفيذها أو خارج مرحلة موظف الموارد.')
        return action, redirect('web:pending_action_detail', action_id=action_id)
    return action, None


@login_required
def settlement_edit_action(request, action_id):
    """يحفظ تعديل أخصائي الموارد على خصومات التصفية (ويُبطل الملف الموقّع السابق)."""
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    from apps.employees.services.settlement_override import OVERRIDE_KEY, parse_override_post
    try:
        with transaction.atomic():
            action, denied = _settlement_guard(request, action_id)
            if denied:
                return denied
            base = _settlement_base_financials(action)
            if base is None:
                messages.error(request, 'تعذّر تحديد تاريخ التصفية من الطلب.')
                return redirect('web:pending_action_detail', action_id=action_id)
            override, errors = parse_override_post(request.POST, request.user, base)
            if errors:
                for error in errors:
                    messages.error(request, error)
                return redirect('web:pending_action_detail', action_id=action_id)
            payload = dict(action.payload or {})
            previous = payload.get(OVERRIDE_KEY) or {}
            ignore = ('edited_at',)
            changed = (
                {k: v for k, v in override.items() if k not in ignore}
                != {k: v for k, v in previous.items() if k not in ignore}
            )
            if override:
                payload[OVERRIDE_KEY] = override
            else:
                payload.pop(OVERRIDE_KEY, None)
            action.payload = payload
            update_fields = ['payload']
            if changed and action.signed_settlement:
                # الأرقام تغيّرت بعد التوقيع → الملف الموقّع القديم لم يعد مطابقاً
                action.signed_settlement = None
                update_fields.append('signed_settlement')
                messages.warning(
                    request,
                    'تغيّرت أرقام التصفية، فأُلغي الملف الموقّع السابق — '
                    'اطبع التصفية ووقّعها ثم ارفعها من جديد.',
                )
            action.save(update_fields=update_fields)
        messages.success(
            request,
            'تم حفظ تعديل التصفية.' if override else 'أُعيدت أرقام التصفية إلى القيم التلقائية.',
        )
    except Exception as e:
        messages.error(request, log_web_action_error('settlement_edit_action', e))
    return redirect('web:pending_action_detail', action_id=action_id)


@login_required
def settlement_signed_upload(request, action_id):
    """يرفع التصفية الموقّعة من المدير المالي — شرط للموافقة النهائية."""
    if request.method != 'POST':
        return redirect('web:pending_action_detail', action_id=action_id)
    from django.core.exceptions import ValidationError
    from apps.core.validators import validate_employee_upload
    upload = request.FILES.get('signed_file')
    if not upload:
        messages.error(request, 'اختر ملف التصفية الموقّع أولاً.')
        return redirect('web:pending_action_detail', action_id=action_id)
    try:
        validate_employee_upload(upload)
        with transaction.atomic():
            action, denied = _settlement_guard(request, action_id)
            if denied:
                return denied
            action.signed_settlement = upload
            action.save(update_fields=['signed_settlement'])
        messages.success(request, 'تم رفع التصفية الموقّعة — يمكنك الآن الموافقة النهائية.')
    except ValidationError as e:
        messages.error(request, ' '.join(e.messages))
    except Exception as e:
        messages.error(request, log_web_action_error('settlement_signed_upload', e))
    return redirect('web:pending_action_detail', action_id=action_id)
