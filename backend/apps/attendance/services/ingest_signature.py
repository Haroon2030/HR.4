"""توقيع HMAC-SHA256 لطلبات ingest وكيل البصمة (+ مكافحة إعادة التشغيل)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from django.conf import settings
from django.core.cache import cache

SIGNATURE_HEADER = 'X-Attendance-Signature'
TIMESTAMP_HEADER = 'X-Attendance-Timestamp'
AUTH_SIGNATURE_PREFIX = 'Attendance-HMAC '
_REPLAY_CACHE_PREFIX = 'att_ingest_replay:'


def get_ingest_body(request) -> bytes:
    """جسم الطلب الخام — يُفضّل النسخة المحفوظة في middleware."""
    cached = getattr(request, '_ingest_raw_body', None)
    if cached is not None:
        return cached
    body = request.body or b''
    if not body and hasattr(request, '_request'):
        body = getattr(request._request, 'body', b'') or b''
    return body


def extract_provided_signature(request) -> str:
    """يقرأ التوقيع من ترويسات متعددة (بعض البروكسيات تحذف X-Attendance-*)."""
    sig = (request.headers.get(SIGNATURE_HEADER) or '').strip()
    if sig:
        return sig
    auth = (request.headers.get('Authorization') or '').strip()
    if auth.lower().startswith(AUTH_SIGNATURE_PREFIX.lower()):
        return auth[len(AUTH_SIGNATURE_PREFIX):].strip()
    return (request.META.get('HTTP_X_ATTENDANCE_SIGNATURE') or '').strip()


def extract_provided_timestamp(request) -> str:
    ts = (request.headers.get(TIMESTAMP_HEADER) or '').strip()
    if ts:
        return ts
    return (request.META.get('HTTP_X_ATTENDANCE_TIMESTAMP') or '').strip()


def ingest_timestamp_skew_seconds() -> int:
    return int(getattr(settings, 'ATTENDANCE_INGEST_TIMESTAMP_SKEW_SECONDS', 300) or 300)


def _signed_payload(body: bytes, *, timestamp: str | None) -> bytes:
    if timestamp:
        return f'{timestamp}.'.encode('utf-8') + body
    return body


def compute_ingest_signature(
    raw_key: str,
    body: bytes,
    *,
    timestamp: str | int | None = None,
) -> str:
    ts = str(timestamp).strip() if timestamp is not None and str(timestamp).strip() else None
    digest = hmac.new(
        raw_key.strip().encode('utf-8'),
        _signed_payload(body, timestamp=ts),
        hashlib.sha256,
    ).hexdigest()
    return f'sha256={digest}'


def verify_ingest_signature(
    raw_key: str,
    body: bytes,
    provided: str,
    *,
    timestamp: str | int | None = None,
) -> bool:
    if not raw_key or not provided:
        return False
    provided = provided.strip()
    expected = compute_ingest_signature(raw_key, body, timestamp=timestamp)
    if provided.startswith('sha256='):
        return secrets.compare_digest(provided, expected)
    bare = expected.split('=', 1)[1]
    return secrets.compare_digest(provided, bare)


def validate_ingest_timestamp(timestamp: str, *, now: float | None = None) -> tuple[bool, str]:
    """يتحقق من وجود الطابع الزمني وضمن نافذة السماح."""
    if not timestamp:
        return False, 'طابع زمني للطلب مطلوب (X-Attendance-Timestamp).'
    try:
        ts = int(str(timestamp).strip())
    except (TypeError, ValueError):
        return False, 'طابع زمني غير صالح.'
    # رفض القيم غير المنطقية (ميلي ثانية بالخطأ)
    if ts > 10_000_000_000:
        return False, 'طابع زمني غير صالح.'
    skew = ingest_timestamp_skew_seconds()
    current = int(now if now is not None else time.time())
    if abs(current - ts) > skew:
        return False, 'انتهت صلاحية توقيع الطلب — تحقق من ساعة الجهاز وأعد المحاولة.'
    return True, ''


def claim_ingest_replay_slot(
    raw_key: str,
    body: bytes,
    *,
    timestamp: str,
) -> bool:
    """
    يحجز فتحة لمرة واحدة لنفس (مفتاح + طابع + جسم).
    True = أول استلام، False = إعادة تشغيل.
    """
    key_fp = hashlib.sha256((raw_key or '').encode('utf-8')).hexdigest()[:16]
    body_fp = hashlib.sha256(body or b'').hexdigest()[:32]
    cache_key = f'{_REPLAY_CACHE_PREFIX}{key_fp}:{timestamp}:{body_fp}'
    ttl = max(ingest_timestamp_skew_seconds() * 2, 60)
    return bool(cache.add(cache_key, '1', timeout=ttl))


def signature_required() -> bool:
    return bool(getattr(settings, 'ATTENDANCE_REQUIRE_INGEST_SIGNATURE', False))
