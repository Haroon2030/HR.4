from django.test import RequestFactory, TestCase, override_settings

from config.middleware import ProxyForwardedHeadersMiddleware


class ProxyForwardedHeadersMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ProxyForwardedHeadersMiddleware(lambda request: request)

    @override_settings(
        USE_HTTPS=True,
        SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    )
    def test_sets_proto_from_forwarded_header(self):
        request = self.factory.get(
            '/health/',
            HTTP_FORWARDED='for=1.2.3.4;proto=https;by=proxy',
        )
        self.middleware(request)
        self.assertEqual(request.META.get('HTTP_X_FORWARDED_PROTO'), 'https')
        self.assertTrue(request.is_secure())

    def test_does_not_override_existing_proto(self):
        request = self.factory.get(
            '/health/',
            HTTP_X_FORWARDED_PROTO='https',
            HTTP_FORWARDED='for=1.2.3.4;proto=http',
        )
        self.middleware(request)
        self.assertEqual(request.META.get('HTTP_X_FORWARDED_PROTO'), 'https')
