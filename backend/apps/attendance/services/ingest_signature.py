"""توقيع HMAC-SHA256 لطلبات ingest وكيل البصمة."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from django.conf import settings

SIGNATURE_HEADER = 'X-Attendance-Signature'
AUTH_SIGNATURE_PREFIX = 'Attendance-HMAC '


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


def compute_ingest_signature(raw_key: str, body: bytes) -> str:
    digest = hmac.new(
        raw_key.strip().encode('utf-8'),
        body,
        hashlib.sha256,
    ).hexdigest()
    return f'sha256={digest}'


def verify_ingest_signature(raw_key: str, body: bytes, provided: str) -> bool:
    if not raw_key or not provided:
        return False
    provided = provided.strip()
    expected = compute_ingest_signature(raw_key, body)
    if provided.startswith('sha256='):
        return secrets.compare_digest(provided, expected)
    bare = expected.split('=', 1)[1]
    return secrets.compare_digest(provided, bare)


def signature_required() -> bool:
    return bool(getattr(settings, 'ATTENDANCE_REQUIRE_INGEST_SIGNATURE', False))
