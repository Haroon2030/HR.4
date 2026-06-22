from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

User = get_user_model()

_LOC_MEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'ratelimit-tests',
    }
}


@override_settings(
    RATELIMIT_ENABLE=True,
    CACHES=_LOC_MEM_CACHE,
    RATELIMIT_LOGIN_IP='2/m',
    RATELIMIT_LOGIN_USER='2/m',
)
class WebLoginRateLimitTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(username='ratelimit_user', password='good-pass')

    def test_login_blocked_after_repeated_failures(self):
        url = reverse('web:auth:login')
        for _ in range(2):
            response = self.client.post(
                url,
                {'username': 'ratelimit_user', 'password': 'wrong-pass'},
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.post(
            url,
            {'username': 'ratelimit_user', 'password': 'wrong-pass'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'تم تجاوز عدد محاولات')


@override_settings(
    RATELIMIT_ENABLE=True,
    CACHES=_LOC_MEM_CACHE,
    RATELIMIT_API_TOKEN_IP='2/m',
)
class JwtRateLimitTests(TestCase):
    def test_token_endpoint_returns_429_when_limited(self):
        url = reverse('token_obtain_pair')
        for _ in range(2):
            response = self.client.post(
                url,
                {'username': 'nobody', 'password': 'wrong'},
                content_type='application/json',
            )
            self.assertIn(response.status_code, (400, 401))

        response = self.client.post(
            url,
            {'username': 'nobody', 'password': 'wrong'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json()['success'])
