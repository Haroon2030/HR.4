"""قوالب واتساب لطلبات الصيانة."""
from __future__ import annotations

from apps.core.services.whatsapp.templates import build_system_link


def _priority_label(req) -> str:
    return req.get_priority_display()


def build_maintenance_created_message(req) -> str:
    return (
        f'🔧 *طلب صيانة جديد*\n'
        f'الفرع: {req.branch.name}\n'
        f'العنوان: {req.title}\n'
        f'الأولوية: {_priority_label(req)}\n'
        f'الوصف: {req.description[:500]}\n'
        f'رابط: {build_system_link(f"/maintenance/requests/{req.id}/")}'
    )


def build_maintenance_assigned_message(req) -> str:
    worker = req.assigned_worker
    report_url = build_system_link(f'/maintenance/report/{req.worker_report_token}/')
    return (
        f'🔧 *مهمة صيانة مُسندة إليك*\n'
        f'الفرع: {req.branch.name}\n'
        f'العنوان: {req.title}\n'
        f'الموقع: {req.location or "—"}\n'
        f'الأولوية: {_priority_label(req)}\n'
        f'الوصف: {req.description[:400]}\n\n'
        f'بعد التنفيذ اضغط الرابط لتأكيد الإنجاز:\n{report_url}'
    )


def build_maintenance_worker_reported_message(req) -> str:
    return (
        f'✅ *بلاغ تنفيذ صيانة*\n'
        f'طلب #{req.id} — {req.title}\n'
        f'العامل: {req.assigned_worker.effective_name if req.assigned_worker else "—"}\n'
        f'ملاحظات: {req.worker_report_notes or "—"}\n'
        f'رابط: {build_system_link(f"/maintenance/requests/{req.id}/")}'
    )


def build_maintenance_manager_closed_message(req) -> str:
    return (
        f'📋 *بانتظار تأكيد الفرع*\n'
        f'طلب صيانة #{req.id}\n'
        f'الفرع: {req.branch.name}\n'
        f'العنوان: {req.title}\n'
        f'رابط: {build_system_link(f"/maintenance/requests/{req.id}/")}'
    )
