"""مصادقة وكيل البصمة المحلي (مفتاح API)."""
from __future__ import annotations

import secrets

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class AttendanceAgentPrincipal:
    """مستخدم وهمي للوكيل — يمرّ IsAuthenticated."""

    is_authenticated = True
    is_active = True
    is_staff = False
    is_superuser = False
    pk = None
    username = 'attendance-agent'

    def __str__(self):
        return self.username


class AgentAPIKeyAuthentication(BaseAuthentication):
    """
    Header: X-Attendance-Agent-Key: <ATTENDANCE_AGENT_API_KEY>
    """

    header_name = 'X-Attendance-Agent-Key'

    def authenticate(self, request):
        expected = (getattr(settings, 'ATTENDANCE_AGENT_API_KEY', None) or '').strip()
        if not expected:
            raise AuthenticationFailed(_('وكيل البصمة غير مُفعّل على الخادم (ATTENDANCE_AGENT_API_KEY).'))

        provided = (request.headers.get(self.header_name) or '').strip()
        if not provided or not secrets.compare_digest(provided, expected):
            raise AuthenticationFailed(_('مفتاح وكيل البصمة غير صحيح.'))

        return (AttendanceAgentPrincipal(), 'agent-api-key')
