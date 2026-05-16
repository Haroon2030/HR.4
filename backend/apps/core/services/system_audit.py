"""تسجيل عمليات أمنية/تشغيلية لا يلتقطها simple_history (مثل تغيير كلمة المرور)."""
from __future__ import annotations

from django.contrib.auth import get_user_model

User = get_user_model()


def _client_ip(request) -> str:
    if request is None:
        return ''
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    return forwarded or request.META.get('REMOTE_ADDR', '') or ''


def log_system_audit(
    *,
    request,
    action: str,
    summary: str,
    details: str = '',
    target_user=None,
) -> None:
    from apps.core.models import SystemAuditLog

    actor = getattr(request, 'user', None) if request else None
    if actor is not None and not getattr(actor, 'is_authenticated', False):
        actor = None

    ip = _client_ip(request) if request else ''
    SystemAuditLog.objects.create(
        actor=actor,
        action=action,
        summary=summary,
        details=details or summary,
        target_user=target_user,
        ip_address=ip[:45] if ip else None,
    )
