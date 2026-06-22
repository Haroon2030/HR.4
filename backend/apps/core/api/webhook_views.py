"""API endpoints لاستقبال أحداث خارجية (بدون csrf_exempt)."""
from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.services.whatsapp import evolution_manager
from apps.core.services.whatsapp.authentication import EvolutionAPIKeyAuthentication
from apps.setup.models import EvolutionWhatsAppSettings

logger = logging.getLogger(__name__)


class EvolutionWebhookView(APIView):
    """
    استقبال أحداث Evolution API (QR، اتصال، رسائل).

    محمي بمفتاح API — DRF لا يفرض CSRF عند عدم استخدام SessionAuthentication.
    """

    authentication_classes = [EvolutionAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}

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
        return Response({'ok': True}, status=status.HTTP_200_OK)
