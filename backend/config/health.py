"""Lightweight health check for reverse proxies and orchestrators."""
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    payload = {'status': 'ok', 'database': 'ok'}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception as exc:
        payload['status'] = 'degraded'
        payload['database'] = 'error'
        payload['error'] = str(exc)[:200]
        return JsonResponse(payload, status=503)
    return JsonResponse(payload)
