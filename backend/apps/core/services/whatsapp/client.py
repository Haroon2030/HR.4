"""HTTP client for Evolution API — send text messages."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class EvolutionAPIError(Exception):
    """Evolution API request failed."""

    def __init__(self, message: str, *, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def _base_url() -> str:
    return (getattr(settings, 'EVOLUTION_API_URL', '') or '').rstrip('/')


def _headers() -> dict[str, str]:
    return {
        'Content-Type': 'application/json',
        'apikey': getattr(settings, 'EVOLUTION_API_KEY', '') or '',
    }


def is_configured() -> bool:
    return bool(
        getattr(settings, 'WHATSAPP_ENABLED', False)
        and _base_url()
        and getattr(settings, 'EVOLUTION_API_KEY', '')
        and getattr(settings, 'EVOLUTION_INSTANCE', '')
    )


def send_text(*, phone: str, text: str, timeout: int | None = None) -> dict[str, Any]:
    """POST /message/sendText/{instance}"""
    if not is_configured():
        raise EvolutionAPIError('Evolution API is not configured')

    instance = settings.EVOLUTION_INSTANCE
    url = f'{_base_url()}/message/sendText/{instance}'
    body = json.dumps({
        'number': phone,
        'text': text,
    }).encode('utf-8')

    req = urllib.request.Request(url, data=body, headers=_headers(), method='POST')
    req_timeout = timeout or getattr(settings, 'EVOLUTION_API_TIMEOUT', 20)

    try:
        with urllib.request.urlopen(req, timeout=req_timeout) as resp:
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        logger.warning('Evolution API HTTP %s: %s', exc.code, detail[:500])
        raise EvolutionAPIError(
            f'Evolution API HTTP {exc.code}',
            status=exc.code,
            payload=detail,
        ) from exc
    except urllib.error.URLError as exc:
        logger.warning('Evolution API connection error: %s', exc)
        raise EvolutionAPIError(f'Evolution API connection error: {exc}') from exc
