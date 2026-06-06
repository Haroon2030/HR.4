"""توقيع HMAC-SHA256 لطلبات ingest وكيل البصمة."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from django.conf import settings

SIGNATURE_HEADER = 'X-Attendance-Signature'


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
