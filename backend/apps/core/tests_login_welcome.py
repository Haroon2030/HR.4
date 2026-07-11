from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class LoginWelcomeToastTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(
            username='welcome_user',
            password='654321',
            first_name='أحمد',
            last_name='محمد',
        )

    def test_login_shows_welcome_name_once_on_dashboard(self):
        login_url = reverse('web:auth:login')
        dashboard_url = reverse('web:dashboard')

        response = self.client.post(
            login_url,
            {'username': 'welcome_user', 'password': '654321'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-welcome="1"')
        self.assertContains(response, 'data-message="أحمد محمد"')

        again = self.client.get(dashboard_url)
        self.assertNotContains(again, 'data-welcome="1"')
