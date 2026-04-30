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
def list_pending_actions(request):
    """قائمة طلبات العمليات السريعة المعلّقة. الأخصائي يرى طلباته، المدير يرى طلبات فروعه."""
    from apps.core.models import PendingAction

    status = request.GET.get('status', 'pending')
    qs = PendingAction.objects.select_related(
        'employee', 'branch', 'requested_by', 'reviewed_by'
    )

    # تصفية بحسب الصلاحية
    if request.user.is_superuser:
        pass
    elif request.user.managed_branches.exists():
        # مدير فرع: يرى طلبات فروعه + طلباته الشخصية
        managed_ids = list(request.user.managed_branches.values_list('id', flat=True))
        from django.db.models import Q
        qs = qs.filter(Q(branch_id__in=managed_ids) | Q(requested_by=request.user))
    else:
        # أخصائي عادي: يرى فقط طلباته
        qs = qs.filter(requested_by=request.user)

    if status in ('pending', 'approved', 'rejected'):
        qs = qs.filter(status=status)

    counts = {
        'pending': qs.model.objects.filter(status='pending').count(),
        'approved': qs.model.objects.filter(status='approved').count(),
        'rejected': qs.model.objects.filter(status='rejected').count(),
    }

    return render(request, 'pages/pending_actions/list.html', {
        'actions': qs.order_by('-requested_at')[:200],
        'current_status': status,
        'counts': counts,
    })


@login_required
def approve_pending_action(request, action_id):
    """موافقة مدير الفرع وتنفيذ العملية (Atomic + select_for_update لمنع التنفيذ المزدوج)."""
    from django.db import transaction
    from django.utils import timezone
    from apps.core.models import PendingAction
    from apps.core.services.pending_actions import execute_pending_action

    if request.method != 'POST':
        return redirect('web:list_pending_actions')

    try:
        with transaction.atomic():
            # قفل الصف لمنع تنفيذ مزدوج عند نقرات متزامنة
            try:
                action = PendingAction.objects.select_for_update().get(id=action_id)
            except PendingAction.DoesNotExist:
                messages.error(request, 'الطلب غير موجود.')
                return redirect('web:list_pending_actions')

            if not _can_review_action(request.user, action):
                messages.error(request, 'لا تملك صلاحية مراجعة هذا الطلب.')
                return redirect('web:list_pending_actions')

            if action.status != PendingAction.Status.PENDING:
                messages.warning(request, 'تم البت في هذا الطلب مسبقاً.')
                return redirect('web:list_pending_actions')

            # حدّث الحالة داخل القفل
            from apps.core.forms import ReviewNotesForm
            notes_form = ReviewNotesForm(request.POST)
            notes_form.is_valid()  # optional
            action.status = PendingAction.Status.APPROVED
            action.reviewed_by = request.user
            action.reviewed_at = timezone.now()
            action.review_notes = notes_form.cleaned_data.get('review_notes', '')
            action.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes'])

            # نفّذ العملية داخل نفس المعاملة — أي فشل يُرجِع كل شيء (rollback تلقائي)
            msg = execute_pending_action(action, request.user)

        messages.success(request, f'تمت الموافقة وتنفيذ العملية: {msg}')
    except Exception as e:
        # سجّل الخطأ على نسخة منفصلة (المعاملة الأصلية تراجعت)
        from apps.core.models import PendingAction
        try:
            stale = PendingAction.objects.get(id=action_id)
            stale.execution_error = str(e)[:1000]
            stale.save(update_fields=['execution_error'])
        except PendingAction.DoesNotExist:
            pass
        messages.error(
            request,
            f'فشل تنفيذ العملية: {e}. تم إرجاع الحالة، يمكنك المحاولة لاحقاً.'
        )

    return redirect('web:list_pending_actions')


@login_required
def reject_pending_action(request, action_id):
    """رفض مدير الفرع للطلب (Atomic + select_for_update)."""
    from django.db import transaction
    from django.utils import timezone
    from apps.core.models import PendingAction

    if request.method != 'POST':
        return redirect('web:list_pending_actions')

    from apps.core.forms import ReviewNotesForm
    notes_form = ReviewNotesForm(request.POST, require_notes=True)
    if not notes_form.is_valid():
        for err in notes_form.errors.values():
            messages.error(request, err[0])
        return redirect('web:list_pending_actions')
    notes = notes_form.cleaned_data['review_notes']

    with transaction.atomic():
        try:
            action = PendingAction.objects.select_for_update().get(id=action_id)
        except PendingAction.DoesNotExist:
            messages.error(request, 'الطلب غير موجود.')
            return redirect('web:list_pending_actions')

        if not _can_review_action(request.user, action):
            messages.error(request, 'لا تملك صلاحية مراجعة هذا الطلب.')
            return redirect('web:list_pending_actions')

        if action.status != PendingAction.Status.PENDING:
            messages.warning(request, 'تم البت في هذا الطلب مسبقاً.')
            return redirect('web:list_pending_actions')

        action.status = PendingAction.Status.REJECTED
        action.reviewed_by = request.user
        action.reviewed_at = timezone.now()
        action.review_notes = notes
        action.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes'])

    messages.success(request, 'تم رفض الطلب.')
    return redirect('web:list_pending_actions')
