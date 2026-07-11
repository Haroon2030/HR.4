"""اختبارات إدارة جلسات الويب."""
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import AppModule, Branch, Company, Permission, Role, UserProfile, UserSession

User = get_user_model()


class UserSessionManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='Main', code='M1', company=cls.company)

        cls.admin_role = Role.objects.create(
            name='Admin',
            role_type=Role.RoleType.ADMIN,
            is_system_role=True,
        )
        cls.employee_role = Role.objects.create(
            name='Employee',
            role_type=Role.RoleType.EMPLOYEE,
        )

        users_mod, _ = AppModule.objects.get_or_create(
            code='users',
            defaults={'name': 'Users', 'icon': 'shield', 'order': 5},
        )
        cls.users_edit, _ = Permission.objects.get_or_create(
            code='users.edit',
            defaults={
                'module': users_mod,
                'operation': Permission.Operation.EDIT,
                'name': 'Edit users',
            },
        )
        cls.users_view, _ = Permission.objects.get_or_create(
            code='users.view',
            defaults={
                'module': users_mod,
                'operation': Permission.Operation.VIEW,
                'name': 'View users',
            },
        )
        cls.admin_role.permissions.add(cls.users_edit, cls.users_view)

        cls.admin_user = User.objects.create_user(
            username='sess_admin',
            password='654321',
        )
        ap = cls.admin_user.profile
        ap.role = cls.admin_role
        ap.branch = cls.branch
        ap.save()
        ap.assigned_branches.add(cls.branch)

        cls.target_user = User.objects.create_user(
            username='sess_target',
            password='654321',
        )
        tp = cls.target_user.profile
        tp.role = cls.employee_role
        tp.branch = cls.branch
        tp.save()

        cls.view_only = User.objects.create_user(
            username='sess_viewer',
            password='654321',
        )
        vp = cls.view_only.profile
        vp.role = cls.employee_role
        vp.branch = cls.branch
        vp.save()
        vp.assigned_branches.add(cls.branch)

    def setUp(self):
        self.client = Client()
        self.admin_client = Client()
        self.target_client = Client()

    def _login_target_via_web(self):
        self.target_client.post(
            reverse('web:auth:login'),
            {'username': 'sess_target', 'password': '654321'},
        )

    def test_login_creates_user_session(self):
        self._login_target_via_web()
        self.assertEqual(
            UserSession.objects.filter(user=self.target_user, revoked_at__isnull=True).count(),
            1,
        )

    def test_admin_can_list_user_sessions(self):
        self._login_target_via_web()
        self.admin_client.login(username='sess_admin', password='654321')
        url = reverse('web:list_user_sessions', kwargs={'user_id': self.target_user.pk})
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sess_target')
        self.assertContains(response, 'hr-act--revoke')

    def test_list_all_sessions_shows_revoke_action(self):
        self._login_target_via_web()
        self.admin_client.login(username='sess_admin', password='654321')
        response = self.admin_client.get(reverse('web:list_all_sessions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hr-act--revoke')
        self.assertContains(response, reverse('web:revoke_session', kwargs={'pk': UserSession.objects.get(user=self.target_user).pk}))

    def test_user_without_edit_permission_cannot_list_sessions(self):
        self.admin_client.login(username='sess_viewer', password='654321')
        url = reverse('web:list_all_sessions')
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_user_can_access_my_sessions(self):
        self._login_target_via_web()
        response = self.target_client.get(reverse('web:auth:my_sessions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'جلساتي')
        self.assertContains(response, 'hr-act--revoke')

    def test_user_can_revoke_own_other_session(self):
        self._login_target_via_web()
        live = UserSession.objects.get(user=self.target_user, revoked_at__isnull=True)
        from django.contrib.sessions.backends.db import SessionStore

        other = SessionStore()
        other.create()
        other_record = UserSession.objects.create(
            user=self.target_user,
            session_key=other.session_key,
            device_label='Other device',
        )

        revoke_url = reverse('web:revoke_session', kwargs={'pk': other_record.pk})
        response = self.target_client.post(revoke_url, {'next': 'mine'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('web:auth:my_sessions'))
        other_record.refresh_from_db()
        self.assertIsNotNone(other_record.revoked_at)
        self.assertFalse(Session.objects.filter(session_key=other.session_key).exists())

        dashboard = self.target_client.get(reverse('web:dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        live.refresh_from_db()
        self.assertIsNone(live.revoked_at)

    def test_revoke_current_session_logs_out(self):
        self._login_target_via_web()
        record = UserSession.objects.get(user=self.target_user, revoked_at__isnull=True)
        revoke_url = reverse('web:revoke_session', kwargs={'pk': record.pk})
        response = self.target_client.post(revoke_url, {'next': 'mine'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('web:auth:login'))
        record.refresh_from_db()
        self.assertIsNotNone(record.revoked_at)

    def test_admin_can_list_own_sessions(self):
        self.admin_client.login(username='sess_admin', password='654321')
        url = reverse('web:list_user_sessions', kwargs={'user_id': self.admin_user.pk})
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sess_admin')

    def test_idle_timeout_logs_out_on_next_request(self):
        self._login_target_via_web()
        record = UserSession.objects.get(user=self.target_user, revoked_at__isnull=True)
        from django.utils import timezone
        from datetime import timedelta

        UserSession.objects.filter(pk=record.pk).update(
            last_seen_at=timezone.now() - timedelta(minutes=11),
        )
        response = self.target_client.get(reverse('web:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('idle=1', response.url)

        record.refresh_from_db()
        self.assertIsNotNone(record.revoked_at)

    def test_active_session_not_logged_out_before_idle_limit(self):
        self._login_target_via_web()
        response = self.target_client.get(reverse('web:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_admin_revoke_logs_out_target_session(self):
        self._login_target_via_web()
        record = UserSession.objects.get(user=self.target_user, revoked_at__isnull=True)
        session_key = record.session_key
        self.assertTrue(Session.objects.filter(session_key=session_key).exists())

        self.admin_client.login(username='sess_admin', password='654321')
        revoke_url = reverse('web:revoke_session', kwargs={'pk': record.pk})
        response = self.admin_client.post(revoke_url)
        self.assertEqual(response.status_code, 302)
        record.refresh_from_db()
        self.assertIsNotNone(record.revoked_at)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

        dashboard = self.target_client.get(reverse('web:dashboard'))
        self.assertEqual(dashboard.status_code, 302)
        self.assertIn(reverse('web:auth:login'), dashboard.url)

    def test_revoke_all_on_admin_password_change(self):
        self._login_target_via_web()
        self.assertEqual(
            UserSession.objects.filter(user=self.target_user, revoked_at__isnull=True).count(),
            1,
        )

        self.admin_client.login(username='sess_admin', password='654321')
        edit_url = reverse('web:edit_user', kwargs={'user_id': self.target_user.pk})
        response = self.admin_client.post(edit_url, {
            'username': 'sess_target',
            'first_name': '',
            'last_name': '',
            'email': '',
            'is_active': 'on',
            'role': self.employee_role.id,
            'branch': self.branch.id,
            'password': '987654',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            UserSession.objects.filter(user=self.target_user, revoked_at__isnull=True).count(),
            0,
        )

    def test_orphan_session_marked_revoked_on_list(self):
        record = UserSession.objects.create(
            user=self.target_user,
            session_key='a' * 40,
            device_label='Test',
        )
        self.assertFalse(Session.objects.filter(session_key=record.session_key).exists())

        self.admin_client.login(username='sess_admin', password='654321')
        url = reverse('web:list_user_sessions', kwargs={'user_id': self.target_user.pk})
        self.admin_client.get(url)
        record.refresh_from_db()
        self.assertIsNotNone(record.revoked_at)
