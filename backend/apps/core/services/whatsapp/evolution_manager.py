"""Evolution API — instance management, QR connect, webhooks."""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings

from apps.core.services.whatsapp.client import EvolutionAPIError, _INSTANCE_RE
from apps.core.services.whatsapp.config import EvolutionRuntimeConfig, get_evolution_runtime_config
from apps.setup.models import DEFAULT_EVOLUTION_WEBHOOK_EVENTS, EvolutionWhatsAppSettings

logger = logging.getLogger(__name__)


def _cfg_from_settings_obj(obj: EvolutionWhatsAppSettings) -> EvolutionRuntimeConfig:
    return EvolutionRuntimeConfig(
        whatsapp_enabled=bool(obj.is_enabled),
        api_url=(obj.api_url or '').strip().rstrip('/'),
        api_key=(obj.api_key or '').strip(),
        instance_name=(obj.instance_name or '').strip(),
        source='db',
    )


def _request(
    method: str,
    path: str,
    *,
    config: EvolutionRuntimeConfig | None = None,
    body: dict | None = None,
    timeout: int | None = None,
) -> Any:
    cfg = config or get_evolution_runtime_config()
    if not cfg.api_url or not cfg.api_key:
        raise EvolutionAPIError('رابط Evolution API أو مفتاح API غير مضبوط')

    url = f'{cfg.api_url}{path}'
    headers = {
        'Content-Type': 'application/json',
        'apikey': cfg.api_key,
    }
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    req_timeout = timeout or getattr(settings, 'EVOLUTION_API_TIMEOUT', 20)

    try:
        with urllib.request.urlopen(req, timeout=req_timeout) as resp:
            raw = resp.read().decode('utf-8')
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        logger.warning('Evolution API %s %s → HTTP %s: %s', method, path, exc.code, detail[:500])
        raise EvolutionAPIError(
            f'Evolution API HTTP {exc.code}',
            status=exc.code,
            payload=detail,
        ) from exc
    except urllib.error.URLError as exc:
        logger.warning('Evolution API connection error: %s', exc)
        raise EvolutionAPIError(f'تعذّر الاتصال بـ Evolution API: {exc}') from exc


def _validate_instance_name(name: str) -> str:
    cleaned = (name or '').strip()
    if not cleaned:
        raise EvolutionAPIError('اسم Instance مطلوب')
    if not _INSTANCE_RE.fullmatch(cleaned):
        raise EvolutionAPIError('اسم Instance يجب أن يكون إنجليزياً (حروف/أرقام/._-)')
    return cleaned


def _extract_qrcode_base64(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ''
    for key in ('base64', 'qrcode', 'qr'):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    nested = payload.get('qrcode')
    if isinstance(nested, dict):
        for key in ('base64', 'code'):
            val = nested.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ''


def _normalize_connection_status(raw: Any) -> str:
    text = str(raw or '').strip().lower()
    if text in {'open', 'connected', 'online'}:
        return EvolutionWhatsAppSettings.ConnectionStatus.OPEN
    if text in {'close', 'closed', 'offline', 'disconnected'}:
        return EvolutionWhatsAppSettings.ConnectionStatus.CLOSE
    if text in {'connecting', 'pairing', 'qrcode'}:
        return EvolutionWhatsAppSettings.ConnectionStatus.CONNECTING
    return EvolutionWhatsAppSettings.ConnectionStatus.UNKNOWN


def fetch_instances(*, config: EvolutionRuntimeConfig | None = None) -> list[dict]:
    data = _request('GET', '/instance/fetchInstances', config=config)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get('instances') or data.get('data')
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def find_instance(instance_name: str, *, config: EvolutionRuntimeConfig | None = None) -> dict | None:
    name = _validate_instance_name(instance_name)
    for item in fetch_instances(config=config):
        item_name = (
            item.get('name')
            or item.get('instanceName')
            or item.get('instance')
            or ''
        )
        if str(item_name).strip() == name:
            return item
    return None


def create_instance(
    instance_name: str,
    *,
    config: EvolutionRuntimeConfig | None = None,
) -> dict:
    name = _validate_instance_name(instance_name)
    body = {
        'instanceName': name,
        'integration': 'WHATSAPP-BAILEYS',
        'qrcode': True,
    }
    return _request('POST', '/instance/create', config=config, body=body)


def connect_instance(
    instance_name: str,
    *,
    config: EvolutionRuntimeConfig | None = None,
) -> dict:
    name = _validate_instance_name(instance_name)
    quoted = urllib.parse.quote(name, safe='')
    data = _request('GET', f'/instance/connect/{quoted}', config=config)
    qrcode = _extract_qrcode_base64(data)
    return {
        'raw': data,
        'qrcode_base64': qrcode,
        'connection_status': _normalize_connection_status(
            (data.get('instance') or {}).get('state')
            if isinstance(data.get('instance'), dict)
            else data.get('state') or data.get('status')
        ),
    }


def fetch_connection_state(
    instance_name: str,
    *,
    config: EvolutionRuntimeConfig | None = None,
) -> str:
    name = _validate_instance_name(instance_name)
    quoted = urllib.parse.quote(name, safe='')
    data = _request('GET', f'/instance/connectionState/{quoted}', config=config)
    if isinstance(data, dict):
        state = data.get('state') or data.get('status') or data.get('instance', {}).get('state')
        return _normalize_connection_status(state)
    return EvolutionWhatsAppSettings.ConnectionStatus.UNKNOWN


def find_webhook(
    instance_name: str,
    *,
    config: EvolutionRuntimeConfig | None = None,
) -> dict:
    name = _validate_instance_name(instance_name)
    quoted = urllib.parse.quote(name, safe='')
    return _request('GET', f'/webhook/find/{quoted}', config=config)


def set_webhook(
    instance_name: str,
    webhook_url: str,
    *,
    events: list[str] | None = None,
    enabled: bool = True,
    config: EvolutionRuntimeConfig | None = None,
) -> dict:
    name = _validate_instance_name(instance_name)
    url = (webhook_url or '').strip()
    if not url:
        raise EvolutionAPIError('رابط Webhook مطلوب')
    if not re.match(r'^https?://', url, re.I):
        raise EvolutionAPIError('رابط Webhook يجب أن يبدأ بـ http:// أو https://')

    event_list = events or list(DEFAULT_EVOLUTION_WEBHOOK_EVENTS)
    quoted = urllib.parse.quote(name, safe='')
    payloads = [
        {
            'webhook': {
                'enabled': enabled,
                'url': url,
                'webhookByEvents': False,
                'webhookBase64': False,
                'events': event_list,
            },
        },
        {
            'enabled': enabled,
            'url': url,
            'webhook_by_events': False,
            'events': event_list,
        },
    ]
    last_exc: EvolutionAPIError | None = None
    for body in payloads:
        try:
            return _request('POST', f'/webhook/set/{quoted}', config=config, body=body)
        except EvolutionAPIError as exc:
            last_exc = exc
            if exc.status not in (400, 422):
                raise
    if last_exc:
        raise last_exc
    raise EvolutionAPIError('تعذّر ضبط Webhook')


def sync_settings_status(settings_obj: EvolutionWhatsAppSettings) -> EvolutionWhatsAppSettings:
    """Refresh connection state from Evolution API and persist."""
    if not settings_obj.has_api_credentials() or not settings_obj.is_instance_valid():
        return settings_obj

    cfg = _cfg_from_settings_obj(settings_obj)
    try:
        settings_obj.connection_status = fetch_connection_state(settings_obj.instance_name, config=cfg)
    except EvolutionAPIError as exc:
        logger.info('Evolution status sync failed: %s', exc)
    from django.utils import timezone
    settings_obj.last_status_sync_at = timezone.now()
    settings_obj.save(update_fields=['connection_status', 'last_status_sync_at'])
    return settings_obj


def apply_qrcode_from_webhook_payload(settings_obj: EvolutionWhatsAppSettings, payload: dict) -> None:
    from django.utils import timezone
    qrcode = _extract_qrcode_base64(payload.get('data') if isinstance(payload.get('data'), dict) else payload)
    if qrcode:
        settings_obj.last_qrcode_base64 = qrcode
    settings_obj.connection_status = EvolutionWhatsAppSettings.ConnectionStatus.CONNECTING
    settings_obj.last_webhook_at = timezone.now()
    settings_obj.save(update_fields=['last_qrcode_base64', 'connection_status', 'last_webhook_at'])


def apply_connection_from_webhook_payload(settings_obj: EvolutionWhatsAppSettings, payload: dict) -> None:
    from django.utils import timezone
    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    state = None
    if isinstance(data, dict):
        state = data.get('state') or data.get('status') or data.get('connection')
    settings_obj.connection_status = _normalize_connection_status(state)
    if settings_obj.connection_status == EvolutionWhatsAppSettings.ConnectionStatus.OPEN:
        settings_obj.last_qrcode_base64 = ''
    settings_obj.last_webhook_at = timezone.now()
    settings_obj.save(update_fields=['connection_status', 'last_qrcode_base64', 'last_webhook_at'])
