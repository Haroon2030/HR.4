"""مصادقة طلبات Evolution API (Webhook) — بدون تعطيل CSRF."""
from __future__ import annotations

import json
import logging
import secrets

from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.core.services.whatsapp.config import get_evolution_runtime_config

logger = logging.getLogger(__name__)


class EvolutionWebhookPrincipal:
    """مستخدم وهمي لـ Evolution webhook — يمرّ IsAuthenticated."""

    is_authenticated = True
    is_active = True
    is_staff = False
    is_superuser = False
    pk = None
    username = 'evolution-webhook'

    def __str__(self):
        return self.username


def _extract_provided_api_key(request) -> str:
    header = (request.headers.get('apikey') or request.META.get('HTTP_APIKEY') or '').strip()
    if header:
        return header

    try:
        body = request._request.body
        if body:
            payload = json.loads(body.decode('utf-8'))
            if isinstance(payload, dict):
                return str(payload.get('apikey') or '').strip()
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        pass
    return ''


class EvolutionAPIKeyAuthentication(BaseAuthentication):
    """
    Header: apikey: <EVOLUTION_API_KEY>

    يُضبط تلقائياً في Evolution عند استدعاء set_webhook (حقل headers).
    احتياطياً: حقل apikey داخل جسم الطلب كما ترسله Evolution.
    """

    def authenticate(self, request):
        expected = (get_evolution_runtime_config().api_key or '').strip()
        if not expected:
            raise AuthenticationFailed(_('Evolution API غير مضبوط (مفتاح API مطلوب).'))

        provided = _extract_provided_api_key(request)
        if not provided:
            raise AuthenticationFailed(_('مفتاح Evolution API مطلوب في رأس apikey.'))

        if not secrets.compare_digest(provided, expected):
            remote = (request.META.get('REMOTE_ADDR') or '-').strip()
            logger.warning(
                'Evolution webhook: مفتاح غير صحيح | path=%s | ip=%s',
                getattr(request, 'path', '-'),
                remote,
            )
            raise AuthenticationFailed(_('مفتاح Evolution API غير صحيح.'))

        return (EvolutionWebhookPrincipal(), 'evolution-api-key')
