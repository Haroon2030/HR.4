"""Middleware لطلبات وكيل البصمة."""
from __future__ import annotations

from django.http.request import UnreadablePostError


class AgentIngestBodyMiddleware:
    """يحفظ جسم طلب ingest خاماً قبل أي معالجة لاحقة (للتحقق من HMAC)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method == 'POST'
            and request.path.startswith('/api/v1/attendance/agent/ingest/')
        ):
            try:
                request._ingest_raw_body = request.body
                request._ingest_body_unreadable = False
            except UnreadablePostError:
                # انقطاع الاتصال من الوكيل قبل اكتمال الإرسال — لا نُسقِط الطلب بـ 500.
                request._body = b''
                request._ingest_raw_body = b''
                request._ingest_body_unreadable = True
        return self.get_response(request)


def ingest_body_unreadable(request) -> bool:
    return bool(getattr(request, '_ingest_body_unreadable', False))
