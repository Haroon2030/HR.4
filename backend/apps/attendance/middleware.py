"""Middleware لطلبات وكيل البصمة."""
from __future__ import annotations


class AgentIngestBodyMiddleware:
    """يحفظ جسم طلب ingest خاماً قبل أي معالجة لاحقة (للتحقق من HMAC)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method == 'POST'
            and request.path.startswith('/api/v1/attendance/agent/ingest/')
        ):
            request._ingest_raw_body = request.body
        return self.get_response(request)
