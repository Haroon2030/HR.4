"""تسجيل تدقيق استقبال بصمات الوكيل وإعادة ربط التسجيل."""
from __future__ import annotations

from apps.attendance.models import AttendanceIngestLog, BiometricEnrollmentAuditLog


def _client_ip(request) -> str:
    if request is None:
        return ''
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    return forwarded or request.META.get('REMOTE_ADDR', '') or ''


def log_ingest_attempt(
    *,
    request,
    device,
    agent_id: str = '',
    status: str,
    signature_valid: bool | None = None,
    punches_received: int = 0,
    imported: int = 0,
    skipped_duplicate: int = 0,
    skipped_time_filter: int = 0,
    users_updated: int = 0,
    message: str = '',
) -> AttendanceIngestLog:
    ip = _client_ip(request)
    user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:255] if request else ''
    return AttendanceIngestLog.objects.create(
        device=device,
        agent_id=(agent_id or '')[:120],
        status=status,
        signature_valid=signature_valid,
        punches_received=punches_received,
        imported=imported,
        skipped_duplicate=skipped_duplicate,
        skipped_time_filter=skipped_time_filter,
        users_updated=users_updated,
        message=message or '',
        client_ip=ip[:45] if ip else None,
        user_agent=user_agent,
    )


def log_enrollment_change(
    *,
    request,
    device,
    device_user_id: int,
    new_employee,
    previous_employee=None,
    device_user_name: str = '',
    action: str,
    punches_relinked: int = 0,
) -> BiometricEnrollmentAuditLog:
    actor = getattr(request, 'user', None) if request else None
    if actor is not None and not getattr(actor, 'is_authenticated', False):
        actor = None
    return BiometricEnrollmentAuditLog.objects.create(
        device=device,
        device_user_id=device_user_id,
        previous_employee=previous_employee,
        new_employee=new_employee,
        device_user_name=(device_user_name or '')[:120],
        action=action,
        punches_relinked=punches_relinked,
        performed_by=actor,
    )
