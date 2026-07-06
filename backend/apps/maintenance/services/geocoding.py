"""تحويل الإحداثيات إلى عنوان — عبر Nominatim من الخادم."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_USER_AGENT = 'HR-Maintenance/1.0 (contact: hr-system)'
_NOMINATIM_REVERSE = 'https://nominatim.openstreetmap.org/reverse'
_TIMEOUT_SEC = 8


def _format_address_ar(payload: dict) -> str:
    """عنوان مختصر بالعربية من مكوّنات Nominatim."""
    address = payload.get('address') or {}
    ordered_keys = (
        'amenity', 'building', 'road', 'neighbourhood', 'suburb',
        'quarter', 'city_district', 'city', 'town', 'village',
        'state', 'country',
    )
    parts: list[str] = []
    seen: set[str] = set()
    for key in ordered_keys:
        value = (address.get(key) or '').strip()
        if not value or value in seen:
            continue
        seen.add(value)
        parts.append(value)
    if parts:
        return '، '.join(parts)
    display = (payload.get('display_name') or '').strip()
    if display:
        return display
    lat = payload.get('lat')
    lon = payload.get('lon')
    if lat is not None and lon is not None:
        return f'الإحداثيات: {lat}، {lon}'
    return ''


def reverse_geocode(lat: float, lng: float) -> dict:
    """
    يُرجع {'address': str, 'lat': str, 'lng': str} أو يرفع ValueError.
    """
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError) as exc:
        raise ValueError('إحداثيات غير صالحة') from exc

    if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
        raise ValueError('إحداثيات خارج النطاق')

    params = urllib.parse.urlencode({
        'format': 'json',
        'lat': f'{lat_f:.7f}',
        'lon': f'{lng_f:.7f}',
        'accept-language': 'ar',
        'zoom': '18',
    })
    url = f'{_NOMINATIM_REVERSE}?{params}'
    request = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/json',
            'User-Agent': _USER_AGENT,
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        logger.warning('reverse geocode HTTP %s', exc.code)
        raise ValueError('تعذّر جلب العنوان') from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning('reverse geocode failed: %s', exc)
        raise ValueError('تعذّر جلب العنوان') from exc

    if not payload or payload.get('error'):
        raise ValueError('لا يوجد عنوان لهذا الموقع')

    address = _format_address_ar(payload)
    if not address:
        raise ValueError('لا يوجد عنوان لهذا الموقع')

    return {
        'address': address,
        'lat': str(payload.get('lat') or lat_f),
        'lng': str(payload.get('lon') or lng_f),
    }
