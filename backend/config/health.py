"""Lightweight health check for reverse proxies and orchestrators."""
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.core.rate_limit import limit_health_check


@require_GET
@limit_health_check
def health(request):
    payload = {'status': 'ok', 'database': 'ok'}
    if request.GET.get('proxy') == '1':
        payload['proxy'] = {
            'x_forwarded_proto': (request.META.get('HTTP_X_FORWARDED_PROTO') or '')[:32],
            'x_forwarded_for': (request.META.get('HTTP_X_FORWARDED_FOR') or '')[:64],
            'x_forwarded_host': (request.META.get('HTTP_X_FORWARDED_HOST') or '')[:64],
            'forwarded': (request.META.get('HTTP_FORWARDED') or '')[:128],
            'is_secure': request.is_secure(),
            'use_https_setting': getattr(settings, 'USE_HTTPS', False),
        }
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception as exc:
        payload['status'] = 'degraded'
        payload['database'] = 'error'
        payload['error'] = str(exc)[:200]
        return JsonResponse(payload, status=503)
    return JsonResponse(payload)
