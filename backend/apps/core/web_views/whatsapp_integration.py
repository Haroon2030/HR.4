"""شاشة ربط WhatsApp عبر Evolution API."""
from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.decorators import permission_required
from apps.core.services.whatsapp.client import EvolutionAPIError
from apps.core.services.whatsapp.config import get_evolution_runtime_config
from apps.core.services.whatsapp import evolution_manager
from apps.setup.forms import EvolutionWhatsAppSettingsForm
from apps.setup.models import EvolutionWhatsAppSettings

logger = logging.getLogger(__name__)


def _webhook_url(request) -> str:
    return request.build_absolute_uri(reverse('web:evolution_webhook'))


def _status_payload(settings_obj: EvolutionWhatsAppSettings, request) -> dict:
    cfg = get_evolution_runtime_config()
    webhook_url = _webhook_url(request)
    qrcode = (settings_obj.last_qrcode_base64 or '').strip()
    if qrcode and not qrcode.startswith('data:'):
        qrcode = f'data:image/png;base64,{qrcode}'

    return {
        'configured': settings_obj.has_api_credentials() and settings_obj.is_instance_valid(),
        'delivery_ready': bool(cfg.whatsapp_enabled and settings_obj.has_api_credentials()),
        'connection_status': settings_obj.connection_status,
        'connection_label': settings_obj.get_connection_status_display(),
        'instance_name': settings_obj.instance_name,
        'api_url': settings_obj.api_url,
        'api_key_masked': settings_obj.api_key_masked(),
        'config_source': cfg.source,
        'webhook_url': webhook_url,
        'webhook_enabled': settings_obj.webhook_enabled,
        'qrcode_base64': qrcode,
        'last_webhook_at': (
            timezone.localtime(settings_obj.last_webhook_at).strftime('%Y-%m-%d %H:%M')
            if settings_obj.last_webhook_at else ''
        ),
        'last_status_sync_at': (
            timezone.localtime(settings_obj.last_status_sync_at).strftime('%Y-%m-%d %H:%M')
            if settings_obj.last_status_sync_at else ''
        ),
        'manager_url': f'{(settings_obj.api_url or "").rstrip("/")}/manager' if settings_obj.api_url else '',
    }


@login_required
@permission_required('system_data.edit')
@require_http_methods(['GET', 'POST'])
def whatsapp_integration(request):
    settings_obj = EvolutionWhatsAppSettings.get_solo()

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save').strip()

        if action == 'refresh_status':
            try:
                evolution_manager.sync_settings_status(settings_obj)
                messages.success(request, 'تم تحديث حالة الاتصال.')
            except EvolutionAPIError as exc:
                messages.error(request, str(exc))
            return redirect(reverse('web:whatsapp_integration'))

        if action == 'create_instance':
            if not settings_obj.has_api_credentials() or not settings_obj.is_instance_valid():
                messages.error(request, 'احفظ رابط API واسم Instance أولاً.')
                return redirect(reverse('web:whatsapp_integration'))
            try:
                existing = evolution_manager.find_instance(settings_obj.instance_name)
                if existing:
                    messages.info(request, f'Instance «{settings_obj.instance_name}» موجود مسبقاً.')
                else:
                    evolution_manager.create_instance(settings_obj.instance_name)
                    messages.success(request, f'تم إنشاء Instance «{settings_obj.instance_name}».')
            except EvolutionAPIError as exc:
                messages.error(request, str(exc))
            return redirect(reverse('web:whatsapp_integration'))

        if action == 'connect_qr':
            if not settings_obj.has_api_credentials() or not settings_obj.is_instance_valid():
                messages.error(request, 'احفظ رابط API واسم Instance أولاً.')
                return redirect(reverse('web:whatsapp_integration'))
            try:
                result = evolution_manager.connect_instance(settings_obj.instance_name)
                if result.get('qrcode_base64'):
                    settings_obj.last_qrcode_base64 = result['qrcode_base64']
                settings_obj.connection_status = (
                    result.get('connection_status')
                    or EvolutionWhatsAppSettings.ConnectionStatus.CONNECTING
                )
                settings_obj.save(update_fields=['last_qrcode_base64', 'connection_status'])
                messages.success(request, 'تم توليد QR — امسحه من تطبيق واتساب.')
            except EvolutionAPIError as exc:
                messages.error(request, str(exc))
            return redirect(reverse('web:whatsapp_integration'))

        if action == 'set_webhook':
            if not settings_obj.has_api_credentials() or not settings_obj.is_instance_valid():
                messages.error(request, 'احفظ رابط API واسم Instance أولاً.')
                return redirect(reverse('web:whatsapp_integration'))
            try:
                evolution_manager.set_webhook(
                    settings_obj.instance_name,
                    _webhook_url(request),
                    events=settings_obj.webhook_events_list(),
                    enabled=settings_obj.webhook_enabled,
                )
                messages.success(request, 'تم ضبط Webhook على Evolution API.')
            except EvolutionAPIError as exc:
                messages.error(request, str(exc))
            return redirect(reverse('web:whatsapp_integration'))

        form = EvolutionWhatsAppSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم حفظ إعدادات WhatsApp.')
            return redirect(reverse('web:whatsapp_integration'))
        messages.error(request, 'تحقق من الحقول المدخلة.')

    else:
        form = EvolutionWhatsAppSettingsForm(instance=settings_obj)

    status = _status_payload(settings_obj, request)
    return render(request, 'pages/setup/whatsapp_integration.html', {
        'form': form,
        'settings_obj': settings_obj,
        'status': status,
        'webhook_events': settings_obj.webhook_events_list(),
    })


@login_required
@permission_required('system_data.edit')
@require_GET
def whatsapp_integration_status(request):
    settings_obj = EvolutionWhatsAppSettings.get_solo()
    try:
        evolution_manager.sync_settings_status(settings_obj)
    except EvolutionAPIError:
        pass
    return JsonResponse(_status_payload(settings_obj, request))


@csrf_exempt
@require_POST
def evolution_webhook(request):
    """استقبال أحداث Evolution API (QR، اتصال، رسائل)."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    settings_obj = EvolutionWhatsAppSettings.get_solo()
    event = str(payload.get('event') or payload.get('type') or '').lower()
    settings_obj.last_webhook_at = timezone.now()

    if 'qrcode' in event:
        evolution_manager.apply_qrcode_from_webhook_payload(settings_obj, payload)
    elif 'connection' in event:
        evolution_manager.apply_connection_from_webhook_payload(settings_obj, payload)
    else:
        settings_obj.save(update_fields=['last_webhook_at'])

    logger.info('Evolution webhook event=%s instance=%s', event, payload.get('instance'))
    return JsonResponse({'ok': True})
