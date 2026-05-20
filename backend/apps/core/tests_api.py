"""
اختبارات واجهة REST API (Django REST Framework).

ملاحظة: المشروع Django + DRF وليس FastAPI.
مصادقة الجلسة (client.login) مطلوبة لمسارات /api/v1/* بسبب AccessControlMiddleware.
مسارات /api/token/* تعمل مع JWT مباشرة.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.core.models import AppModule, Branch, Company, Permission, Role, UserProfile

User = get_user_model()


class _SessionAuthenticatedAPIClient(APITestCase):
    """أساس مشترك: مستخدم superuser + تسجيل دخول بالجلسة."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة API')
        cls.branch = Branch.objects.create(
            name='فرع الاختبار',
            code='API-TST',
            company=cls.company,
        )
        cls.role = Role.objects.create(
            name='دور API',
            role_type=Role.RoleType.ADMIN,
        )
        cls.user = User.objects.create_user(
            username='api_superuser',
            password='Api-Test-Pass-99!',
            is_staff=True,
            is_superuser=True,
        )
        profile, _ = UserProfile.objects.get_or_create(user=cls.user)
        profile.role = cls.role
        profile.save(update_fields=['role'])

    def setUp(self):
        self.client = APIClient()
        self.assertTrue(
            self.client.login(username='api_superuser', password='Api-Test-Pass-99!'),
        )

    @staticmethod
    def _results(response):
        data = response.json()
        if isinstance(data, dict) and 'results' in data:
            return data['results']
        return data


class HealthEndpointTests(APITestCase):
    def test_health_returns_ok(self):
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class PublicAPIAccessTests(APITestCase):
    def test_me_requires_authentication(self):
        response = self.client.get('/api/v1/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_branches_list_requires_authentication(self):
        response = self.client.get('/api/v1/branches/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(
    SIMPLE_JWT={
        'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
        'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
        'ROTATE_REFRESH_TOKENS': False,
        'BLACKLIST_AFTER_ROTATION': False,
    },
)
class JWTTokenAPITests(APITestCase):
    """مسارات /api/token/* — خارج فحص AccessControlMiddleware."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='jwt_user',
            password='Jwt-Test-Pass-88!',
        )

    def test_obtain_token_pair(self):
        response = self.client.post(
            '/api/token/',
            {'username': 'jwt_user', 'password': 'Jwt-Test-Pass-88!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn('access', body)
        self.assertIn('refresh', body)

    def test_obtain_token_invalid_credentials(self):
        response = self.client.post(
            '/api/token/',
            {'username': 'jwt_user', 'password': 'wrong-password'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_and_verify_token(self):
        obtain = self.client.post(
            '/api/token/',
            {'username': 'jwt_user', 'password': 'Jwt-Test-Pass-88!'},
            format='json',
        )
        refresh = obtain.json()['refresh']
        access = obtain.json()['access']

        refreshed = self.client.post(
            '/api/token/refresh/',
            {'refresh': refresh},
            format='json',
        )
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertIn('access', refreshed.json())

        verified = self.client.post(
            '/api/token/verify/',
            {'token': access},
            format='json',
        )
        self.assertEqual(verified.status_code, status.HTTP_200_OK)

    def test_jwt_bearer_alone_blocked_on_v1_by_middleware(self):
        """JWT صالح لا يكفي لـ /api/v1/* — Middleware يفحص الجلسة أولاً."""
        obtain = self.client.post(
            '/api/token/',
            {'username': 'jwt_user', 'password': 'Jwt-Test-Pass-88!'},
            format='json',
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {obtain.json()["access"]}')
        response = client.get('/api/v1/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CurrentUserAPITests(_SessionAuthenticatedAPIClient):
    def test_current_user_me(self):
        response = self.client.get('/api/v1/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['username'], 'api_superuser')
        self.assertEqual(data['role'], self.role.id)
        self.assertIn('permissions', data)
        self.assertTrue(data.get('is_superuser'))


class CompanyAPITests(_SessionAuthenticatedAPIClient):
    def test_list_companies(self):
        response = self.client.get('/api/v1/companies/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [c['name'] for c in self._results(response)]
        self.assertIn('شركة API', names)

    def test_retrieve_company(self):
        response = self.client.get(f'/api/v1/companies/{self.company.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['name'], 'شركة API')

    def test_create_and_update_company(self):
        created = self.client.post(
            '/api/v1/companies/',
            {'name': 'شركة جديدة', 'tax_number': '300000000000003'},
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        company_id = created.json()['id']

        updated = self.client.patch(
            f'/api/v1/companies/{company_id}/',
            {'contact_phone': '0500000000'},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.json()['contact_phone'], '0500000000')


class BranchAPITests(_SessionAuthenticatedAPIClient):
    def test_list_branches(self):
        response = self.client.get('/api/v1/branches/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [b['id'] for b in self._results(response)]
        self.assertIn(self.branch.id, ids)

    def test_retrieve_branch(self):
        response = self.client.get(f'/api/v1/branches/{self.branch.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['code'], 'API-TST')

    def test_create_branch(self):
        response = self.client.post(
            '/api/v1/branches/',
            {
                'name': 'فرع جديد',
                'code': 'API-NEW',
                'company': self.company.pk,
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['code'], 'API-NEW')

    def test_branch_employees_action(self):
        response = self.client.get(f'/api/v1/branches/{self.branch.pk}/employees/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.json(), list)


class RoleAPITests(_SessionAuthenticatedAPIClient):
    def test_list_roles(self):
        response = self.client.get('/api/v1/roles/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r['name'] for r in self._results(response)]
        self.assertIn('دور API', names)

    def test_retrieve_role(self):
        response = self.client.get(f'/api/v1/roles/{self.role.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['role_type'], Role.RoleType.ADMIN)


class UserAPITests(_SessionAuthenticatedAPIClient):
    def test_list_users(self):
        response = self.client.get('/api/v1/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [u['username'] for u in self._results(response)]
        self.assertIn('api_superuser', usernames)

    def test_users_roles_action(self):
        response = self.client.get('/api/v1/users/roles/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(r['name'] == 'دور API' for r in response.json()))

    def test_assign_role_to_user(self):
        target = User.objects.create_user(
            username='api_target_user',
            password='Target-Pass-77!',
        )
        response = self.client.post(
            f'/api/v1/users/{target.pk}/assign_role/',
            {'role_id': self.role.pk},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target.refresh_from_db()
        self.assertEqual(target.profile.role_id, self.role.pk)


class RBACRestrictedAPITests(APITestCase):
    """مستخدم بدون صلاحيات — يجب أن يُرفض على قوائم محمية."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة RBAC')
        module, _ = AppModule.objects.get_or_create(
            code='branches',
            defaults={'name': 'الفروع', 'order': 1},
        )
        Permission.objects.get_or_create(
            code='branches.view',
            defaults={
                'module': module,
                'operation': Permission.Operation.VIEW,
                'name': 'عرض الفروع',
            },
        )
        cls.restricted_role = Role.objects.create(
            name='دور بدون صلاحيات',
            role_type=Role.RoleType.EMPLOYEE,
        )
        cls.restricted_user = User.objects.create_user(
            username='api_restricted',
            password='Restricted-Pass-66!',
        )
        profile, _ = UserProfile.objects.get_or_create(user=cls.restricted_user)
        profile.role = cls.restricted_role
        profile.save(update_fields=['role'])

    def setUp(self):
        self.client = APIClient()
        self.assertTrue(
            self.client.login(username='api_restricted', password='Restricted-Pass-66!'),
        )

    def test_branches_list_forbidden_without_permission(self):
        response = self.client.get('/api/v1/branches/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
