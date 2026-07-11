"""تتبع وإدارة جلسات الويب (django_session) — للأدمن."""
from __future__ import annotations

import re
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.core.services.system_audit import _client_ip, log_system_audit


def get_idle_timeout() -> timedelta:
    from django.conf import settings

    seconds = int(getattr(settings, 'SESSION_IDLE_TIMEOUT', 600) or 600)
    return timedelta(seconds=max(seconds, 60))


def apply_session_idle_expiry(request) -> None:
    """ضبط مدة جلسة django_session حسب مهلة الخمول."""
    from django.conf import settings

    timeout = int(getattr(settings, 'SESSION_IDLE_TIMEOUT', 600) or 600)
    request.session.set_expiry(max(timeout, 60))


def idle_timeout_message() -> str:
    from django.conf import settings

    minutes = max(int(getattr(settings, 'SESSION_IDLE_TIMEOUT', 600) or 600) // 60, 1)
    return f'انتهت جلستك بسبب {minutes} دقائق بدون نشاط. يُرجى تسجيل الدخول مجدداً.'


def enforce_idle_timeout(request) -> bool:
    """إنهاء الجلسة إذا تجاوزت مهلة الخمول. يُرجع True إذا تم تسجيل الخروج."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return False

    session_key = getattr(request.session, 'session_key', None)
    if not session_key:
        return False

    from apps.core.models import UserSession

    record = UserSession.objects.filter(
        session_key=session_key,
        revoked_at__isnull=True,
    ).only('pk', 'session_key', 'last_seen_at', 'user_id', 'device_label', 'ip_address').first()

    now = timezone.now()
    idle_limit = get_idle_timeout()

    if record is None:
        register_session(request, request.user)
        apply_session_idle_expiry(request)
        return False

    if record.last_seen_at > now - idle_limit:
        return False

    from django.contrib.auth import logout

    revoke_session_record(record, actor=request.user, request=request, log=False)
    logout(request)
    return True


def parse_device_label(user_agent: str) -> str:
    """تسمية مقروءة للجهاز/المتصفح من User-Agent."""
    ua = (user_agent or '').strip()
    if not ua:
        return 'جهاز غير معروف'

    browser = 'متصفح'
    if 'Edg/' in ua or 'Edge/' in ua:
        browser = 'Edge'
    elif 'Chrome/' in ua and 'Chromium' not in ua:
        browser = 'Chrome'
    elif 'Firefox/' in ua:
        browser = 'Firefox'
    elif 'Safari/' in ua and 'Chrome' not in ua:
        browser = 'Safari'
    elif 'MSIE' in ua or 'Trident/' in ua:
        browser = 'Internet Explorer'

    platform = 'غير معروف'
    if re.search(r'Windows NT', ua, re.I):
        platform = 'Windows'
    elif re.search(r'Mac OS X|Macintosh', ua, re.I):
        platform = 'macOS'
    elif re.search(r'Android', ua, re.I):
        platform = 'Android'
    elif re.search(r'iPhone|iPad|iPod', ua, re.I):
        platform = 'iOS'
    elif re.search(r'Linux', ua, re.I):
        platform = 'Linux'

    return f'{browser} · {platform}'


def _session_key_tail(session_key: str) -> str:
    key = (session_key or '').strip()
    return key[-8:] if len(key) >= 8 else key


def register_session(request, user) -> None:
    """تسجيل جلسة جديدة بعد login()."""
    from apps.core.models import UserSession

    session_key = getattr(request.session, 'session_key', None)
    if not session_key or not user or not user.pk:
        return

    ua = (request.META.get('HTTP_USER_AGENT') or '')[:512]
    ip = _client_ip(request) or None

    UserSession.objects.update_or_create(
        session_key=session_key,
        defaults={
            'user_id': user.pk,
            'ip_address': ip,
            'user_agent': ua,
            'device_label': parse_device_label(ua),
            'revoked_at': None,
            'revoked_by_id': None,
        },
    )
    apply_session_idle_expiry(request)


def touch_session(request) -> None:
    """تحديث last_seen_at عند كل طلب نشط."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return

    session_key = getattr(request.session, 'session_key', None)
    if not session_key:
        return

    from apps.core.models import UserSession

    now = timezone.now()
    updated = UserSession.objects.filter(
        session_key=session_key,
        revoked_at__isnull=True,
    ).update(last_seen_at=now)
    if not updated:
        register_session(request, request.user)


def _purge_orphan_sessions(queryset) -> None:
    """إنهاء UserSession التي لا يوجد لها صف في django_session."""
    keys = list(queryset.values_list('session_key', flat=True))
    if not keys:
        return
    live_keys = set(
        Session.objects.filter(session_key__in=keys).values_list('session_key', flat=True)
    )
    orphan_keys = [k for k in keys if k not in live_keys]
    if orphan_keys:
        from apps.core.models import UserSession

        now = timezone.now()
        UserSession.objects.filter(
            session_key__in=orphan_keys,
            revoked_at__isnull=True,
        ).update(revoked_at=now)


def list_active_sessions(user=None):
    """جلسات نشطة — اختيارياً لمستخدم واحد."""
    from apps.core.models import UserSession

    qs = UserSession.objects.filter(revoked_at__isnull=True).select_related(
        'user', 'revoked_by',
    )
    if user is not None:
        qs = qs.filter(user=user)
    _purge_orphan_sessions(qs)
    return qs.filter(revoked_at__isnull=True).order_by('-last_seen_at')


def list_active_sessions_for_users(user_ids):
    """جلسات نشطة لمجموعة مستخدمين."""
    from apps.core.models import UserSession

    if not user_ids:
        return UserSession.objects.none()
    qs = UserSession.objects.filter(
        user_id__in=user_ids,
        revoked_at__isnull=True,
    ).select_related('user', 'revoked_by')
    _purge_orphan_sessions(qs)
    return qs.filter(revoked_at__isnull=True).order_by('-last_seen_at')


def revoke_session_record(session_record, *, actor, request=None, log=True) -> bool:
    """حذف django_session ووضع revoked_at."""
    from apps.core.models import SystemAuditLog, UserSession

    if not isinstance(session_record, UserSession):
        session_record = UserSession.objects.filter(pk=session_record).first()
    if not session_record or session_record.revoked_at:
        return False

    Session.objects.filter(session_key=session_record.session_key).delete()
    session_record.revoked_at = timezone.now()
    session_record.revoked_by = actor if getattr(actor, 'is_authenticated', False) else None
    session_record.save(update_fields=['revoked_at', 'revoked_by'])

    if log:
        log_system_audit(
            request=request,
            action=SystemAuditLog.Action.SESSION_REVOKE,
            summary=f'إنهاء جلسة للمستخدم «{session_record.user.get_username()}»',
            details=(
                f'جهاز: {session_record.device_label or "—"}. '
                f'IP: {session_record.ip_address or "—"}. '
                f'مفتاح الجلسة (آخر 8): …{_session_key_tail(session_record.session_key)}'
            ),
            target_user=session_record.user,
        )
    return True


def revoke_session_by_key(session_key, *, actor, request=None, log=True) -> bool:
    from apps.core.models import UserSession

    record = UserSession.objects.filter(
        session_key=session_key,
        revoked_at__isnull=True,
    ).first()
    if not record:
        Session.objects.filter(session_key=session_key).delete()
        return False
    return revoke_session_record(record, actor=actor, request=request, log=log)


def revoke_all_sessions(
    user,
    *,
    actor,
    request=None,
    except_session_key: str | None = None,
) -> int:
    """إنهاء كل جلسات المستخدم — مع استثناء اختياري."""
    from apps.core.models import SystemAuditLog, UserSession

    qs = UserSession.objects.filter(user=user, revoked_at__isnull=True)
    if except_session_key:
        qs = qs.exclude(session_key=except_session_key)

    records = list(qs)
    if not records:
        return 0

    keys = [r.session_key for r in records]
    Session.objects.filter(session_key__in=keys).delete()
    now = timezone.now()
    actor_user = actor if getattr(actor, 'is_authenticated', False) else None
    UserSession.objects.filter(pk__in=[r.pk for r in records]).update(
        revoked_at=now,
        revoked_by=actor_user,
    )

    log_system_audit(
        request=request,
        action=SystemAuditLog.Action.SESSION_REVOKE_ALL,
        summary=f'إنهاء {len(records)} جلسة للمستخدم «{user.get_username()}»',
        details=f'تم إنهاء {len(records)} جلسة ويب نشطة.',
        target_user=user,
    )
    return len(records)


def count_active_sessions(user) -> int:
    return list_active_sessions(user).count()
