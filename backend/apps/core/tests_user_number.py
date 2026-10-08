"""رقم المستخدم فريد: رسالة واضحة بدل IntegrityError عند التكرار."""
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import UserProfile

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class UserNumberUniquenessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='num_admin', password='x-pass-123')
        self.owner = User.objects.create_user(username='owner', password='x-pass-123')
        UserProfile.objects.filter(user=self.owner).update(user_number='1001')
        self.other = User.objects.create_user(username='other', password='x-pass-123')
        self.client.force_login(self.admin)

    def _messages(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    def test_edit_with_number_of_another_user_shows_error_not_500(self):
        url = reverse('web:edit_user', kwargs={'user_id': self.other.pk})
        response = self.client.post(url, {'username': 'other', 'user_number': '1001'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any('مستخدم بالفعل' in m for m in self._messages(response)))
        self.other.profile.refresh_from_db()
        self.assertIsNone(self.other.profile.user_number)

    def test_edit_keeping_own_number_is_allowed(self):
        url = reverse('web:edit_user', kwargs={'user_id': self.owner.pk})
        self.client.post(url, {'username': 'owner', 'user_number': '1001'})
        self.owner.profile.refresh_from_db()
        self.assertEqual(self.owner.profile.user_number, '1001')

    def test_add_with_taken_number_shows_error(self):
        response = self.client.post(reverse('web:add_user'), {
            'username': 'newbie', 'password': '123456', 'user_number': '1001',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newbie').exists())
        self.assertTrue(any('مستخدم بالفعل' in m for m in self._messages(response)))

    def test_blank_number_for_many_users_is_allowed(self):
        url = reverse('web:edit_user', kwargs={'user_id': self.other.pk})
        response = self.client.post(url, {'username': 'other', 'user_number': '  '})
        self.assertNotEqual(response.status_code, 500)
        self.other.profile.refresh_from_db()
        self.assertIsNone(self.other.profile.user_number)

    def test_password_only_change_without_user_number_keeps_other_data(self):
        """تغيير كلمة المرور فقط: لا يُطلب رقم مستخدم، ولا يُمسح الجوال/المسمى."""
        UserProfile.objects.filter(user=self.other).update(phone='0500000000', position='محاسب')
        url = reverse('web:edit_user', kwargs={'user_id': self.other.pk})
        response = self.client.post(url, {'username': 'other', 'password': '654321'})
        self.assertEqual(response.status_code, 302)
        self.other.refresh_from_db()
        self.assertTrue(self.other.check_password('654321'))
        profile = UserProfile.objects.get(user=self.other)
        self.assertEqual((profile.phone, profile.position), ('0500000000', 'محاسب'))

    def test_edit_page_does_not_require_user_number(self):
        url = reverse('web:edit_user', kwargs={'user_id': self.other.pk})
        html = self.client.get(url).content.decode()
        tag = html[html.index('name="user_number"'):]
        tag = tag[:tag.index('>')]
        self.assertNotIn('required', tag)
