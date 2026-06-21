"""Tests for Evolution WhatsApp integration."""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.setup.models import EvolutionWhatsAppSettings


class EvolutionManagerTests(TestCase):
    def setUp(self):
        self.settings_obj = EvolutionWhatsAppSettings.get_solo()
        self.settings_obj.api_url = 'http://evolution.test:8081'
        self.settings_obj.api_key = 'secret-key'
        self.settings_obj.instance_name = 'hr'
        self.settings_obj.save()

    @patch('apps.core.services.whatsapp.evolution_manager.urllib.request.urlopen')
    def test_set_webhook_posts_payload(self, mock_urlopen):
        from apps.core.services.whatsapp.evolution_manager import set_webhook

        mock_urlopen.return_value.__enter__.return_value = BytesIO(
            b'{"ok": true}'
        )
        result = set_webhook('hr', 'https://hr.test/webhooks/evolution/')
        self.assertEqual(result['ok'], True)
        req = mock_urlopen.call_args[0][0]
        self.assertIn('/webhook/set/hr', req.full_url)
        body = json.loads(req.data.decode())
        self.assertTrue(body['webhook']['enabled'])
        self.assertEqual(body['webhook']['url'], 'https://hr.test/webhooks/evolution/')

    @patch('apps.core.services.whatsapp.evolution_manager.urllib.request.urlopen')
    def test_connect_instance_extracts_qrcode(self, mock_urlopen):
        from apps.core.services.whatsapp.evolution_manager import connect_instance

        mock_urlopen.return_value.__enter__.return_value = BytesIO(
            json.dumps({
                'base64': 'data:image/png;base64,AAA',
                'state': 'connecting',
            }).encode(),
        )
        result = connect_instance('hr')
        self.assertEqual(result['qrcode_base64'], 'data:image/png;base64,AAA')
        self.assertEqual(result['connection_status'], EvolutionWhatsAppSettings.ConnectionStatus.CONNECTING)


@override_settings(ALLOWED_HOSTS=['testserver'])
class WhatsAppIntegrationViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username='wa_admin', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        EvolutionWhatsAppSettings.get_solo()

    def test_integration_page_loads(self):
        resp = self.client.get(reverse('web:whatsapp_integration'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ربط WhatsApp')

    def test_webhook_accepts_qrcode_event(self):
        url = reverse('web:evolution_webhook')
        payload = {
            'event': 'qrcode.updated',
            'data': {'qrcode': {'base64': 'data:image/png;base64,BBB'}},
        }
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        obj = EvolutionWhatsAppSettings.get_solo()
        self.assertIn('BBB', obj.last_qrcode_base64)
        self.assertEqual(obj.connection_status, EvolutionWhatsAppSettings.ConnectionStatus.CONNECTING)

    @patch('apps.core.services.whatsapp.evolution_manager.urllib.request.urlopen')
    def test_status_endpoint_returns_json(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = BytesIO(
            json.dumps({'state': 'open'}).encode(),
        )
        resp = self.client.get(reverse('web:whatsapp_integration_status'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('connection_status', data)
        self.assertIn('webhook_url', data)
