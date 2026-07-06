"""منطق سير طلبات الصيانة."""
from __future__ import annotations

import secrets

from django.db import transaction
from django.utils import timezone

from apps.maintenance.models import MaintenanceRequest, MaintenanceWorker


class MaintenanceWorkflowError(Exception):
    pass


def _generate_worker_token() -> str:
    return secrets.token_urlsafe(32)


def create_maintenance_request(*, branch, title, description, requested_by,
                               location='', priority=MaintenanceRequest.Priority.NORMAL,
                               attachment=None, asset=None) -> MaintenanceRequest:
    req = MaintenanceRequest.objects.create(
        branch=branch,
        asset=asset,
        title=title.strip(),
        description=description.strip(),
        location=(location or '').strip(),
        priority=priority or MaintenanceRequest.Priority.NORMAL,
        attachment=attachment,
        requested_by=requested_by,
        status=MaintenanceRequest.Status.PENDING,
    )
    from apps.maintenance.services import notifications
    notifications.notify_request_created(req)
    from apps.maintenance.services.sidebar_counts import invalidate_maintenance_sidebar_caches
    invalidate_maintenance_sidebar_caches(req)
    return req


@transaction.atomic
def assign_maintenance_request(*, request: MaintenanceRequest, worker: MaintenanceWorker,
                               assigned_by) -> MaintenanceRequest:
    if request.status not in (
        MaintenanceRequest.Status.PENDING,
        MaintenanceRequest.Status.RETURNED,
    ):
        raise MaintenanceWorkflowError('لا يمكن إسناد الطلب في هذه الحالة.')
    if not worker.is_active or worker.is_deleted:
        raise MaintenanceWorkflowError('العامل غير نشط.')
    if not worker.effective_phone:
        raise MaintenanceWorkflowError('العامل لا يملك رقم جوال لإرسال واتساب.')

    request.status = MaintenanceRequest.Status.ASSIGNED
    request.assigned_worker = worker
    request.assigned_by = assigned_by
    request.assigned_at = timezone.now()
    request.worker_report_token = _generate_worker_token()
    request.worker_report_notes = ''
    request.worker_reported_at = None
    request.return_notes = ''
    request.returned_by = None
    request.returned_at = None
    request.save(update_fields=[
        'status', 'assigned_worker', 'assigned_by', 'assigned_at',
        'worker_report_token', 'worker_report_notes', 'worker_reported_at',
        'return_notes', 'returned_by', 'returned_at', 'updated_at',
    ])

    from apps.maintenance.services import notifications
    notifications.notify_worker_assigned(request)
    from apps.maintenance.services.sidebar_counts import invalidate_maintenance_sidebar_caches
    invalidate_maintenance_sidebar_caches(request)
    return request


@transaction.atomic
def worker_report_completion(*, request: MaintenanceRequest, notes: str = '') -> MaintenanceRequest:
    if request.status != MaintenanceRequest.Status.ASSIGNED:
        raise MaintenanceWorkflowError('الطلب غير متاح للتبليغ.')
    request.status = MaintenanceRequest.Status.WORKER_REPORTED
    request.worker_report_notes = (notes or '').strip()
    request.worker_reported_at = timezone.now()
    request.save(update_fields=[
        'status', 'worker_report_notes', 'worker_reported_at', 'updated_at',
    ])

    from apps.maintenance.services import notifications
    notifications.notify_worker_reported(request)
    from apps.maintenance.services.sidebar_counts import invalidate_maintenance_sidebar_caches
    invalidate_maintenance_sidebar_caches(request)
    return request


@transaction.atomic
def manager_close_request(*, request: MaintenanceRequest, closed_by,
                          notes: str = '') -> MaintenanceRequest:
    if request.status != MaintenanceRequest.Status.WORKER_REPORTED:
        raise MaintenanceWorkflowError('الطلب ليس بانتظار إغلاق مدير الصيانة.')
    request.status = MaintenanceRequest.Status.MANAGER_CLOSED
    request.manager_closed_by = closed_by
    request.manager_closed_at = timezone.now()
    request.manager_notes = (notes or '').strip()
    request.save(update_fields=[
        'status', 'manager_closed_by', 'manager_closed_at', 'manager_notes', 'updated_at',
    ])

    from apps.maintenance.services import notifications
    notifications.notify_manager_closed(request)
    from apps.maintenance.services.sidebar_counts import invalidate_maintenance_sidebar_caches
    invalidate_maintenance_sidebar_caches(request)
    return request


@transaction.atomic
def branch_confirm_request(*, request: MaintenanceRequest, confirmed_by) -> MaintenanceRequest:
    if request.status != MaintenanceRequest.Status.MANAGER_CLOSED:
        raise MaintenanceWorkflowError('الطلب ليس بانتظار تأكيد الفرع.')
    request.status = MaintenanceRequest.Status.BRANCH_CONFIRMED
    request.branch_confirmed_by = confirmed_by
    request.branch_confirmed_at = timezone.now()
    request.save(update_fields=[
        'status', 'branch_confirmed_by', 'branch_confirmed_at', 'updated_at',
    ])

    from apps.maintenance.services import notifications
    notifications.notify_branch_confirmed(request)
    from apps.maintenance.services.sidebar_counts import invalidate_maintenance_sidebar_caches
    invalidate_maintenance_sidebar_caches(request)
    return request


@transaction.atomic
def return_maintenance_request(*, request: MaintenanceRequest, returned_by,
                               notes: str) -> MaintenanceRequest:
    if request.status not in (
        MaintenanceRequest.Status.PENDING,
        MaintenanceRequest.Status.ASSIGNED,
    ):
        raise MaintenanceWorkflowError('لا يمكن إرجاع الطلب في هذه الحالة.')
    if not (notes or '').strip():
        raise MaintenanceWorkflowError('ملاحظات الإرجاع مطلوبة.')

    request.status = MaintenanceRequest.Status.RETURNED
    request.return_notes = notes.strip()
    request.returned_by = returned_by
    request.returned_at = timezone.now()
    request.assigned_worker = None
    request.assigned_by = None
    request.assigned_at = None
    request.worker_report_token = ''
    request.save(update_fields=[
        'status', 'return_notes', 'returned_by', 'returned_at',
        'assigned_worker', 'assigned_by', 'assigned_at', 'worker_report_token', 'updated_at',
    ])

    from apps.maintenance.services import notifications
    notifications.notify_request_returned(request)
    from apps.maintenance.services.sidebar_counts import invalidate_maintenance_sidebar_caches
    invalidate_maintenance_sidebar_caches(request)
    return request


@transaction.atomic
def resubmit_maintenance_request(*, request: MaintenanceRequest, user) -> MaintenanceRequest:
    if request.status != MaintenanceRequest.Status.RETURNED:
        raise MaintenanceWorkflowError('الطلب غير مرتجع.')
    if request.requested_by_id != user.id:
        raise MaintenanceWorkflowError('فقط مُقدّم الطلب يمكنه إعادة الإرسال.')

    request.status = MaintenanceRequest.Status.PENDING
    request.return_notes = ''
    request.returned_by = None
    request.returned_at = None
    request.resubmit_count += 1
    request.save(update_fields=[
        'status', 'return_notes', 'returned_by', 'returned_at',
        'resubmit_count', 'updated_at',
    ])

    from apps.maintenance.services import notifications
    notifications.notify_request_created(request)
    from apps.maintenance.services.sidebar_counts import invalidate_maintenance_sidebar_caches
    invalidate_maintenance_sidebar_caches(request)
    return request
