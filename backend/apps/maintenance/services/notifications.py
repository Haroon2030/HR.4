"""إشعارات داخلية وواتساب لطلبات الصيانة."""
from __future__ import annotations

from django.urls import reverse

from apps.core.models import Notification
from apps.core.services import notifications as notif_svc
from apps.maintenance.services.recipients import branch_manager_for_request, maintenance_manager_users


def _detail_url(request_id: int) -> str:
    return reverse('web:maintenance_request_detail', kwargs={'request_id': request_id})


def notify_request_created(req):
    link = _detail_url(req.id)
    title = f'طلب صيانة جديد — {req.branch.name}'
    message = req.title
    for user in maintenance_manager_users():
        notif_svc.notify(
            user,
            title=title,
            message=message,
            link=link,
            icon='wrench',
            color=Notification.Color.AMBER,
        )
    from apps.maintenance.services import whatsapp_notifier
    whatsapp_notifier.notify_maintenance_created(req)


def notify_worker_assigned(req):
    from apps.maintenance.services import whatsapp_notifier
    whatsapp_notifier.notify_maintenance_assigned(req)


def notify_worker_reported(req):
    link = _detail_url(req.id)
    title = f'بلاغ تنفيذ — طلب صيانة #{req.id}'
    message = req.title
    for user in maintenance_manager_users():
        notif_svc.notify(
            user,
            title=title,
            message=message,
            link=link,
            icon='wrench',
            color=Notification.Color.INDIGO,
        )
    from apps.maintenance.services import whatsapp_notifier
    whatsapp_notifier.notify_maintenance_worker_reported(req)


def notify_manager_closed(req):
    link = _detail_url(req.id)
    title = f'بانتظار تأكيد الفرع — طلب صيانة #{req.id}'
    message = req.title
    manager = branch_manager_for_request(req)
    if manager:
        notif_svc.notify(
            manager,
            title=title,
            message=message,
            link=link,
            icon='wrench',
            color=Notification.Color.PRIMARY,
        )
    if req.requested_by_id and (not manager or req.requested_by_id != manager.id):
        notif_svc.notify(
            req.requested_by,
            title=title,
            message=message,
            link=link,
            icon='wrench',
            color=Notification.Color.PRIMARY,
        )
    from apps.maintenance.services import whatsapp_notifier
    whatsapp_notifier.notify_maintenance_manager_closed(req)


def notify_branch_confirmed(req):
    link = _detail_url(req.id)
    title = f'اكتمل طلب الصيانة #{req.id}'
    message = req.title
    if req.requested_by_id:
        notif_svc.notify(
            req.requested_by,
            title=title,
            message=message,
            link=link,
            icon='wrench',
            color=Notification.Color.EMERALD,
        )


def notify_request_returned(req):
    link = _detail_url(req.id)
    title = f'طلب صيانة مرتجع — #{req.id}'
    message = req.return_notes or req.title
    if req.requested_by_id:
        notif_svc.notify(
            req.requested_by,
            title=title,
            message=message,
            link=link,
            icon='wrench',
            color=Notification.Color.RED,
        )
