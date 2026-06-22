"""شاشة ربط WhatsApp عبر Evolution API."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.decorators import permission_required
from apps.core.services.whatsapp.client import EvolutionAPIError
from apps.core.services.whatsapp.config import get_evolution_runtime_config
from apps.core.services.whatsapp import evolution_manager
from apps.setup.forms import EvolutionWhatsAppSettingsForm
from apps.setup.models import EvolutionWhatsAppSettings


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


def _display_settings(settings_obj: EvolutionWhatsAppSettings, form=None) -> EvolutionWhatsAppSettings:
    """عرض القيم المُدخلة حتى قبل الحفظ (عند أخطاء التحقق)."""
    if form is not None and form.is_bound:
        for field in ('api_url', 'instance_name', 'is_enabled', 'webhook_enabled'):
            if field in form.data:
                val = form.data.get(field)
                if field in ('is_enabled', 'webhook_enabled'):
                    setattr(settings_obj, field, val in ('on', 'true', 'True', '1'))
                else:
                    setattr(settings_obj, field, (val or '').strip())
    return settings_obj


def _apply_settings_from_post(request, settings_obj: EvolutionWhatsAppSettings):
    """
    يحفظ الإعدادات إذا وُجدت حقول النموذج في الطلب (مع أي زر: حفظ / QR / webhook).
    """
    if 'api_url' not in request.POST and 'instance_name' not in request.POST:
        return settings_obj, None, False

    form = EvolutionWhatsAppSettingsForm(request.POST, instance=settings_obj)
    if not form.is_valid():
        return settings_obj, form, False

    saved = form.save()
    return saved, form, True


@login_required
@permission_required('system_data.edit')
@require_http_methods(['GET', 'POST'])
def whatsapp_integration(request):
    settings_obj = EvolutionWhatsAppSettings.get_solo()
    form = None

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save').strip()
        settings_obj, form, saved = _apply_settings_from_post(request, settings_obj)

        if action != 'save' and form is not None and not saved:
            messages.error(request, 'صحّح أخطاء الإعدادات قبل تنفيذ العملية.')
            status = _status_payload(_display_settings(settings_obj, form), request)
            return render(request, 'pages/setup/whatsapp_integration.html', {
                'form': form,
                'settings_obj': settings_obj,
                'status': status,
                'webhook_events': settings_obj.webhook_events_list(),
            })

        if action == 'save':
            if saved:
                messages.success(request, 'تم حفظ إعدادات WhatsApp.')
            elif form is not None and not form.is_valid():
                messages.error(request, 'تحقق من الحقول المدخلة.')
                status = _status_payload(_display_settings(settings_obj, form), request)
                return render(request, 'pages/setup/whatsapp_integration.html', {
                    'form': form,
                    'settings_obj': settings_obj,
                    'status': status,
                    'webhook_events': settings_obj.webhook_events_list(),
                })
            return redirect(reverse('web:whatsapp_integration'))

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

        messages.error(request, 'إجراء غير معروف.')
        return redirect(reverse('web:whatsapp_integration'))

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
