"""مصادقة وكيل البصمة المحلي (مفتاح API عام أو مفتاح لكل جهاز)."""
from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.attendance.services.agent_keys import find_device_by_agent_key

logger = logging.getLogger(__name__)


class AttendanceAgentPrincipal:
    """مستخدم وهمي للوكيل — يمرّ IsAuthenticated."""

    is_authenticated = True
    is_active = True
    is_staff = False
    is_superuser = False
    pk = None
    username = 'attendance-agent'

    def __init__(self, *, device=None, is_global_key: bool = False, api_key_presented: str = ''):
        self.device = device
        self.is_global_key = is_global_key
        self.api_key_presented = (api_key_presented or '').strip()
        if device is not None:
            self.username = f'attendance-agent-device-{device.pk}'

    def __str__(self):
        return self.username


class AgentAPIKeyAuthentication(BaseAuthentication):
    """
    Header: X-Attendance-Agent-Key: <key>
    (توافق: X-Agent-Key يُقبل أيضاً)

    - مفتاح عام (ATTENDANCE_AGENT_API_KEY) — وصول كامل (توافق خلفي).
    - مفتاح جهاز — يُقيَّد بجهاز البصمة المطابق في ingest/ack.
    """

    header_name = 'X-Attendance-Agent-Key'
    legacy_header_name = 'X-Agent-Key'

    def _extract_api_key(self, request) -> tuple[str, str]:
        """يرجع (المفتاح, المصدر: primary|legacy|none)."""
        primary = (request.headers.get(self.header_name) or '').strip()
        if primary:
            return primary, 'primary'
        legacy = (request.headers.get(self.legacy_header_name) or '').strip()
        if legacy:
            return legacy, 'legacy'
        return '', 'none'

    def authenticate(self, request):
        global_key = (getattr(settings, 'ATTENDANCE_AGENT_API_KEY', None) or '').strip()
        provided, _key_source = self._extract_api_key(request)

        if not provided:
            if not global_key:
                raise AuthenticationFailed(
                    _('وكيل البصمة غير مُفعّل (ATTENDANCE_AGENT_API_KEY أو مفتاح جهاز).')
                )
            raise AuthenticationFailed(
                _(
                    'مفتاح وكيل البصمة مطلوب. '
                    'استخدم الهيدر X-Attendance-Agent-Key (أو X-Agent-Key للتوافق).'
                )
            )

        if global_key and secrets.compare_digest(provided, global_key):
            return (
                AttendanceAgentPrincipal(is_global_key=True, api_key_presented=provided),
                'agent-api-key',
            )

        device = find_device_by_agent_key(provided)
        if device:
            return (
                AttendanceAgentPrincipal(device=device, api_key_presented=provided),
                'agent-api-key',
            )

        remote = (request.META.get('REMOTE_ADDR') or '-').strip()
        logger.warning(
            'وكيل البصمة: مفتاح غير صحيح | path=%s | ip=%s | ua=%s',
            getattr(request, 'path', '-'),
            remote,
            ((request.META.get('HTTP_USER_AGENT') or '')[:80] or '-'),
        )
        raise AuthenticationFailed(_('مفتاح وكيل البصمة غير صحيح.'))
