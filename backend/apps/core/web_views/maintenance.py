"""واجهات إدارة الصيانة — طلبات، عمال، مهن."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.decorators import has_permission, permission_required
from apps.maintenance.forms import (
    MaintenanceAssetForm,
    MaintenanceRequestForm,
    MaintenanceTradeForm,
    MaintenanceWorkerForm,
    WorkerReportForm,
)
from apps.maintenance.models import MaintenanceAsset, MaintenanceRequest, MaintenanceTrade, MaintenanceWorker
from apps.maintenance.services.access import filter_requests_for_user, user_sees_all_maintenance
from apps.maintenance.services.geocoding import reverse_geocode as reverse_geocode_coords
from apps.maintenance.services.setup import get_maintenance_setup_tab_context, resolve_setup_tab
from apps.maintenance.services.requests import (
    MaintenanceWorkflowError,
    assign_maintenance_request,
    branch_confirm_request,
    create_maintenance_request,
    manager_close_request,
    resubmit_maintenance_request,
    return_maintenance_request,
    worker_report_completion,
)


def _setup_url(tab: str = 'assets') -> str:
    return reverse('web:maintenance_setup') + f'?tab={resolve_setup_tab(tab)}'


TAB_STATUS_MAP = {
    'all': None,
    'pending': MaintenanceRequest.Status.PENDING,
    'assigned': MaintenanceRequest.Status.ASSIGNED,
    'worker_reported': MaintenanceRequest.Status.WORKER_REPORTED,
    'manager_closed': MaintenanceRequest.Status.MANAGER_CLOSED,
    'branch_confirmed': MaintenanceRequest.Status.BRANCH_CONFIRMED,
    'returned': MaintenanceRequest.Status.RETURNED,
    'mine': 'mine',
}


def _requests_queryset():
    return MaintenanceRequest.objects.select_related(
        'branch', 'asset', 'requested_by', 'assigned_worker', 'assigned_worker__trade',
        'assigned_by', 'manager_closed_by', 'branch_confirmed_by', 'returned_by',
    )


def _can_assign(user) -> bool:
    return user.is_superuser or has_permission(user, 'maintenance.assign')


def _can_manage(user) -> bool:
    return user.is_superuser or has_permission(user, 'maintenance.manage')


def _can_confirm_branch(user, req) -> bool:
    if not (user.is_superuser or has_permission(user, 'maintenance.confirm_branch')):
        return False
    if user_sees_all_maintenance(user):
        return True
    from apps.core.services.access_control import get_accessible_branch_ids
    branch_ids = get_accessible_branch_ids(user)
    if branch_ids is None:
        return True
    return req.branch_id in branch_ids


def _can_return(user) -> bool:
    return user.is_superuser or has_permission(user, 'maintenance.return')


@login_required
@permission_required('maintenance.view')
def list_maintenance_requests(request):
    tab = (request.GET.get('tab') or 'all').strip()
    if tab not in TAB_STATUS_MAP:
        tab = 'all'

    qs = filter_requests_for_user(request.user, _requests_queryset())
    query = (request.GET.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(branch__name__icontains=query)
            | Q(location__icontains=query),
        )

    status_filter = TAB_STATUS_MAP[tab]
    if status_filter == 'mine':
        qs = qs.filter(requested_by=request.user)
    elif status_filter:
        qs = qs.filter(status=status_filter)

    qs = qs.order_by('-requested_at', '-id')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    counts = {}
    base = filter_requests_for_user(request.user, MaintenanceRequest.objects.all())
    for key, st in TAB_STATUS_MAP.items():
        if st == 'mine':
            counts[key] = base.filter(requested_by=request.user).count()
        elif st:
            counts[key] = base.filter(status=st).count()
        else:
            counts[key] = base.count()

    return render(request, 'pages/maintenance/requests/list.html', {
        'page_obj': page_obj,
        'requests': page_obj.object_list,
        'tab': tab,
        'query': query,
        'counts': counts,
        'can_add': has_permission(request.user, 'maintenance.add'),
        'can_assign': _can_assign(request.user),
    })


@login_required
@permission_required('maintenance.add')
def add_maintenance_request(request):
    if request.method == 'POST':
        form = MaintenanceRequestForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            req = create_maintenance_request(
                branch=form.cleaned_data['branch'],
                title=form.cleaned_data['title'],
                description=form.cleaned_data['description'],
                location=form.cleaned_data.get('location', ''),
                priority=form.cleaned_data.get('priority'),
                attachment=form.cleaned_data.get('attachment'),
                asset=form.cleaned_data.get('asset'),
                requested_by=request.user,
            )
            messages.success(request, f'تم إرسال طلب الصيانة #{req.id} إلى مدير الصيانة.')
            return redirect('web:maintenance_request_detail', request_id=req.id)
    else:
        form = MaintenanceRequestForm(user=request.user)

    return render(request, 'pages/maintenance/requests/form.html', {
        'form': form,
    })


@login_required
@permission_required('maintenance.view')
def maintenance_request_detail(request, request_id):
    qs = filter_requests_for_user(request.user, _requests_queryset())
    req = get_object_or_404(qs, pk=request_id)

    workers = MaintenanceWorker.objects.filter(
        is_deleted=False, is_active=True,
    ).select_related('trade', 'employee').order_by('name')

    return render(request, 'pages/maintenance/requests/detail.html', {
        'req': req,
        'workers': workers,
        'can_assign': _can_assign(request.user) and req.status in (
            MaintenanceRequest.Status.PENDING, MaintenanceRequest.Status.RETURNED,
        ),
        'can_manage': _can_manage(request.user) and req.status == MaintenanceRequest.Status.WORKER_REPORTED,
        'can_confirm': _can_confirm_branch(request.user, req) and req.status == MaintenanceRequest.Status.MANAGER_CLOSED,
        'can_return': _can_return(request.user) and req.status in (
            MaintenanceRequest.Status.PENDING, MaintenanceRequest.Status.ASSIGNED,
        ),
        'can_resubmit': (
            req.status == MaintenanceRequest.Status.RETURNED
            and req.requested_by_id == request.user.id
        ),
    })


@login_required
@permission_required('maintenance.assign')
@require_http_methods(['POST'])
def assign_maintenance_request_view(request, request_id):
    qs = filter_requests_for_user(request.user, MaintenanceRequest.objects.all())
    req = get_object_or_404(qs, pk=request_id)
    worker_id = (request.POST.get('worker_id') or '').strip()
    if not worker_id.isdigit():
        messages.error(request, 'اختر عامل صيانة.')
        return redirect('web:maintenance_request_detail', request_id=req.id)

    worker = get_object_or_404(
        MaintenanceWorker.objects.filter(is_deleted=False, is_active=True),
        pk=int(worker_id),
    )
    try:
        assign_maintenance_request(request=req, worker=worker, assigned_by=request.user)
        messages.success(request, f'تم إسناد الطلب إلى {worker.effective_name} وإرسال واتساب.')
    except MaintenanceWorkflowError as exc:
        messages.error(request, str(exc))
    return redirect('web:maintenance_request_detail', request_id=req.id)


@login_required
@permission_required('maintenance.manage')
@require_http_methods(['POST'])
def manager_close_maintenance_request(request, request_id):
    qs = filter_requests_for_user(request.user, MaintenanceRequest.objects.all())
    req = get_object_or_404(qs, pk=request_id)
    notes = (request.POST.get('manager_notes') or '').strip()
    try:
        manager_close_request(request=req, closed_by=request.user, notes=notes)
        messages.success(request, 'تم إغلاق الطلب وإرساله لتأكيد مدير الفرع.')
    except MaintenanceWorkflowError as exc:
        messages.error(request, str(exc))
    return redirect('web:maintenance_request_detail', request_id=req.id)


@login_required
@permission_required('maintenance.confirm_branch')
@require_http_methods(['POST'])
def branch_confirm_maintenance_request(request, request_id):
    qs = filter_requests_for_user(request.user, MaintenanceRequest.objects.all())
    req = get_object_or_404(qs, pk=request_id)
    if not _can_confirm_branch(request.user, req):
        messages.error(request, 'لا تملك صلاحية تأكيد هذا الطلب.')
        return redirect('web:maintenance_request_detail', request_id=req.id)
    try:
        branch_confirm_request(request=req, confirmed_by=request.user)
        messages.success(request, 'تم تأكيد إنجاز طلب الصيانة.')
    except MaintenanceWorkflowError as exc:
        messages.error(request, str(exc))
    return redirect('web:maintenance_request_detail', request_id=req.id)


@login_required
@permission_required('maintenance.return')
@require_http_methods(['POST'])
def return_maintenance_request_view(request, request_id):
    qs = filter_requests_for_user(request.user, MaintenanceRequest.objects.all())
    req = get_object_or_404(qs, pk=request_id)
    notes = (request.POST.get('return_notes') or '').strip()
    try:
        return_maintenance_request(request=req, returned_by=request.user, notes=notes)
        messages.success(request, 'تم إرجاع الطلب.')
    except MaintenanceWorkflowError as exc:
        messages.error(request, str(exc))
    return redirect('web:maintenance_request_detail', request_id=req.id)


@login_required
@permission_required('maintenance.add')
@require_http_methods(['POST'])
def resubmit_maintenance_request_view(request, request_id):
    qs = filter_requests_for_user(request.user, MaintenanceRequest.objects.all())
    req = get_object_or_404(qs, pk=request_id)
    try:
        resubmit_maintenance_request(request=req, user=request.user)
        messages.success(request, 'تم إعادة إرسال الطلب.')
    except MaintenanceWorkflowError as exc:
        messages.error(request, str(exc))
    return redirect('web:maintenance_request_detail', request_id=req.id)


@ratelimit(key='ip', rate='30/h', method='POST', block=True)
@csrf_protect
@require_http_methods(['GET', 'POST'])
def worker_report_maintenance(request, token):
    """صفحة عامة للعامل — تأكيد التنفيذ بدون تسجيل دخول."""
    token = (token or '').strip()
    if not token:
        raise Http404
    req = MaintenanceRequest.objects.select_related(
        'branch', 'assigned_worker',
    ).filter(worker_report_token=token, is_deleted=False).first()
    if not req:
        raise Http404

    if req.status == MaintenanceRequest.Status.BRANCH_CONFIRMED:
        return render(request, 'pages/maintenance/report_done.html', {'req': req, 'already': True})

    if req.status != MaintenanceRequest.Status.ASSIGNED:
        return render(request, 'pages/maintenance/report_done.html', {
            'req': req,
            'already': True,
            'message': 'تم تسجيل البلاغ مسبقاً أو الطلب غير متاح.',
        })

    if request.method == 'POST':
        form = WorkerReportForm(request.POST)
        if form.is_valid():
            try:
                worker_report_completion(
                    request=req,
                    notes=form.cleaned_data.get('notes', ''),
                )
                return render(request, 'pages/maintenance/report_done.html', {
                    'req': req,
                    'success': True,
                })
            except MaintenanceWorkflowError as exc:
                messages.error(request, str(exc))
    else:
        form = WorkerReportForm()

    return render(request, 'pages/maintenance/report_form.html', {
        'req': req,
        'form': form,
    })


# ── تهيئة الصيانة (تبويبات) ─────────────────────────────────────────────────

@login_required
@permission_required('maintenance.workers_view')
def maintenance_setup(request):
    tab = resolve_setup_tab(request.GET.get('tab'))
    return render(request, 'pages/maintenance/setup/list.html', {
        'active_tab': tab,
        'setup_tab_url': reverse('web:maintenance_setup_tab'),
    })


@login_required
@permission_required('maintenance.workers_view')
def maintenance_setup_tab(request):
    tab = resolve_setup_tab(request.GET.get('tab'))
    ctx = get_maintenance_setup_tab_context(request.user, tab)
    return render(request, 'pages/maintenance/setup/_tab.html', ctx)


# ── أصول الصيانة ───────────────────────────────────────────────────────────

@login_required
@permission_required('maintenance.workers_add')
def add_maintenance_asset(request):
    if request.method == 'POST':
        form = MaintenanceAssetForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تمت إضافة الأصل.')
            return redirect(_setup_url('assets'))
    else:
        form = MaintenanceAssetForm()
    return render(request, 'pages/maintenance/setup/asset_form.html', {
        'form': form,
        'title': 'إضافة أصل',
    })


@login_required
@permission_required('maintenance.workers_edit')
def edit_maintenance_asset(request, asset_id):
    asset = get_object_or_404(MaintenanceAsset, pk=asset_id, is_deleted=False)
    if request.method == 'POST':
        form = MaintenanceAssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث الأصل.')
            return redirect(_setup_url('assets'))
    else:
        form = MaintenanceAssetForm(instance=asset)
    return render(request, 'pages/maintenance/setup/asset_form.html', {
        'form': form,
        'title': 'تعديل أصل',
        'asset': asset,
    })


@login_required
@permission_required('maintenance.workers_delete')
@require_http_methods(['POST'])
def delete_maintenance_asset(request, asset_id):
    asset = get_object_or_404(MaintenanceAsset, pk=asset_id, is_deleted=False)
    if MaintenanceRequest.objects.filter(asset=asset, is_deleted=False).exists():
        messages.error(request, 'لا يمكن حذف أصل مرتبط بطلبات صيانة.')
    else:
        asset.delete()
        messages.success(request, 'تم حذف الأصل.')
    return redirect(_setup_url('assets'))


# ── تهيئة المهن ─────────────────────────────────────────────────────────────

@login_required
@permission_required('maintenance.workers_view')
def list_maintenance_trades(request):
    return redirect(_setup_url('trades'))


@login_required
@permission_required('maintenance.workers_add')
def add_maintenance_trade(request):
    if request.method == 'POST':
        form = MaintenanceTradeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تمت إضافة المهنة.')
            return redirect(_setup_url('trades'))
    else:
        form = MaintenanceTradeForm()
    return render(request, 'pages/maintenance/trades/form.html', {
        'form': form,
        'title': 'إضافة مهنة صيانة',
        'back_url': _setup_url('trades'),
    })


@login_required
@permission_required('maintenance.workers_edit')
def edit_maintenance_trade(request, trade_id):
    trade = get_object_or_404(MaintenanceTrade, pk=trade_id, is_deleted=False)
    if request.method == 'POST':
        form = MaintenanceTradeForm(request.POST, instance=trade)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث المهنة.')
            return redirect(_setup_url('trades'))
    else:
        form = MaintenanceTradeForm(instance=trade)
    return render(request, 'pages/maintenance/trades/form.html', {
        'form': form,
        'title': 'تعديل مهنة صيانة',
        'trade': trade,
        'back_url': _setup_url('trades'),
    })


@login_required
@permission_required('maintenance.workers_delete')
@require_http_methods(['POST'])
def delete_maintenance_trade(request, trade_id):
    trade = get_object_or_404(MaintenanceTrade, pk=trade_id, is_deleted=False)
    if MaintenanceWorker.objects.filter(trade=trade, is_deleted=False).exists():
        messages.error(request, 'لا يمكن حذف مهنة مرتبطة بعمال.')
    else:
        trade.delete()
        messages.success(request, 'تم حذف المهنة.')
    return redirect(_setup_url('trades'))


# ── تهيئة العمال ────────────────────────────────────────────────────────────

@login_required
@permission_required('maintenance.workers_view')
def list_maintenance_workers(request):
    return redirect(_setup_url('workers'))


@login_required
@permission_required('maintenance.workers_add')
def add_maintenance_worker(request):
    if request.method == 'POST':
        form = MaintenanceWorkerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تمت إضافة عامل الصيانة.')
            return redirect(_setup_url('workers'))
    else:
        form = MaintenanceWorkerForm()
    return render(request, 'pages/maintenance/workers/form.html', {
        'form': form,
        'title': 'إضافة عامل صيانة',
        'employee_search_url': reverse('web:employee_picker_search'),
        'back_url': _setup_url('workers'),
    })


@login_required
@permission_required('maintenance.workers_edit')
def edit_maintenance_worker(request, worker_id):
    worker = get_object_or_404(MaintenanceWorker, pk=worker_id, is_deleted=False)
    if request.method == 'POST':
        form = MaintenanceWorkerForm(request.POST, instance=worker)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث عامل الصيانة.')
            return redirect(_setup_url('workers'))
    else:
        form = MaintenanceWorkerForm(instance=worker)
    return render(request, 'pages/maintenance/workers/form.html', {
        'form': form,
        'title': 'تعديل عامل صيانة',
        'worker': worker,
        'employee_search_url': reverse('web:employee_picker_search'),
        'back_url': _setup_url('workers'),
    })


@login_required
@permission_required('maintenance.add')
@require_http_methods(['GET'])
@ratelimit(key='user', rate='30/m', block=True)
def maintenance_reverse_geocode(request):
    """تحويل إحداثيات GPS إلى عنوان فعلي (لنموذج طلب الصيانة)."""
    lat_raw = request.GET.get('lat')
    lng_raw = request.GET.get('lng')
    try:
        result = reverse_geocode_coords(lat_raw, lng_raw)
    except ValueError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)
    return JsonResponse({
        'success': True,
        'data': result,
    })


@login_required
@permission_required('maintenance.workers_delete')
@require_http_methods(['POST'])
def delete_maintenance_worker(request, worker_id):
    worker = get_object_or_404(MaintenanceWorker, pk=worker_id, is_deleted=False)
    worker.delete()
    messages.success(request, 'تم حذف عامل الصيانة.')
    return redirect(_setup_url('workers'))
