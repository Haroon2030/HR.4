"""HTTP client for Evolution API — send text and media messages."""
from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Literal

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
    instance = (getattr(settings, 'EVOLUTION_INSTANCE', '') or '').strip()
    return bool(
        getattr(settings, 'WHATSAPP_ENABLED', False)
        and _base_url()
        and getattr(settings, 'EVOLUTION_API_KEY', '')
        and instance
        and _INSTANCE_RE.fullmatch(instance)
    )


_INSTANCE_RE = re.compile(r'^[A-Za-z0-9._-]+$')


def _validate_instance(instance: str) -> str:
    name = (instance or '').strip()
    if not name:
        raise EvolutionAPIError('EVOLUTION_INSTANCE غير مضبوط')
    if not _INSTANCE_RE.fullmatch(name):
        raise EvolutionAPIError(
            'EVOLUTION_INSTANCE يجب أن يكون اسماً إنجليزياً (حروف/أرقام فقط) — '
            'مثل hr أو main. استخدم: python manage.py test_whatsapp --list-instances'
        )
    return name


def send_text(*, phone: str, text: str, timeout: int | None = None) -> dict[str, Any]:
    """POST /message/sendText/{instance}"""
    if not is_configured():
        raise EvolutionAPIError('Evolution API is not configured')

    instance = _validate_instance(settings.EVOLUTION_INSTANCE)
    url = f'{_base_url()}/message/sendText/{urllib.parse.quote(instance, safe="")}'
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


MediaType = Literal['image', 'document', 'video', 'audio']


def send_media(
    *,
    phone: str,
    mediatype: MediaType,
    media: str,
    file_name: str = '',
    mimetype: str = '',
    caption: str = '',
    timeout: int | None = None,
) -> dict[str, Any]:
    """POST /message/sendMedia/{instance}"""
    if not is_configured():
        raise EvolutionAPIError('Evolution API is not configured')

    instance = _validate_instance(settings.EVOLUTION_INSTANCE)
    url = f'{_base_url()}/message/sendMedia/{urllib.parse.quote(instance, safe="")}'
    payload: dict[str, Any] = {
        'number': phone,
        'mediatype': mediatype,
        'media': media,
    }
    if file_name:
        payload['fileName'] = file_name
    if mimetype:
        payload['mimetype'] = mimetype
    if caption:
        payload['caption'] = caption

    body = json.dumps(payload).encode('utf-8')
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


def _encode_media_base64(data: bytes) -> str:
    """Evolution API v2 يتوقع base64 خاماً بدون بادئة data URI."""
    return base64.b64encode(data).decode('ascii')


def send_document(
    *,
    phone: str,
    pdf_bytes: bytes,
    file_name: str,
    caption: str = '',
    timeout: int | None = None,
) -> dict[str, Any]:
    """Send a PDF document via base64-encoded media."""
    if not file_name:
        raise EvolutionAPIError('file_name مطلوب لإرسال المستند')
    if not pdf_bytes:
        raise EvolutionAPIError('ملف PDF فارغ')

    media = _encode_media_base64(pdf_bytes)
    doc_timeout = max(timeout or getattr(settings, 'EVOLUTION_API_TIMEOUT', 20), 60)
    return send_media(
        phone=phone,
        mediatype='document',
        media=media,
        file_name=file_name,
        mimetype='application/pdf',
        caption=caption,
        timeout=doc_timeout,
    )
