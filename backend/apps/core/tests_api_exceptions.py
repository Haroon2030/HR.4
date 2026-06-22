from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from apps.core.exceptions import custom_api_exception_handler


class CustomApiExceptionHandlerTests(TestCase):
    def _call_handler(self, exc):
        request = MagicMock()
        request.path = '/api/v1/test/'
        return custom_api_exception_handler(exc, {'request': request, 'view': None})

    @override_settings(DEBUG=False)
    def test_500_hides_exception_details_in_production(self):
        response = self._call_handler(RuntimeError('secret-database-password'))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('errors', response.data)
        self.assertNotIn('secret', str(response.data))

    @override_settings(DEBUG=True)
    def test_500_includes_exception_details_when_debug(self):
        response = self._call_handler(RuntimeError('dev-only-detail'))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data['errors'], 'dev-only-detail')
