"""صلاحيات أنواع النماذج الرسمية (hr_form_<key>.view)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.hr_form_permissions import HR_FORM_KEYS, hr_form_permission_code
from apps.core.models import Branch, Company, Permission, Role
from apps.core.permission_policy import hr_form_allowed_for_user
from apps.core.web_views.hr_forms import HR_FORMS
from apps.employees.models import Employee

User = get_user_model()


class HRFormPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='B1', code='B1', company=company)
        cls.employee = Employee.objects.create(name='موظف', branch=cls.branch)

        base_codes = ['hr_forms.view', 'employees.view']
        cls.role_legacy = Role.objects.create(name='Legacy', role_type=Role.RoleType.SPECIALIST)
        cls.role_legacy.permissions.set(Permission.objects.filter(code__in=base_codes))

        cls.role_scoped = Role.objects.create(name='Scoped', role_type=Role.RoleType.HR_OFFICER)
        cls.role_scoped.permissions.set(Permission.objects.filter(
            code__in=[*base_codes, hr_form_permission_code('leave_request')],
        ))

        cls.legacy_user = cls._user('legacy', cls.role_legacy)
        cls.scoped_user = cls._user('scoped', cls.role_scoped)
        cls.admin = User.objects.create_superuser(username='root', password='Pass-User-99!', email='r@e.co')

    @classmethod
    def _user(cls, username, role):
        user = User.objects.create_user(username=username, password='Pass-User-99!')
        profile = user.profile
        profile.role = role
        profile.branch = cls.branch
        profile.save()
        return user

    def test_form_types_match_catalog(self):
        self.assertEqual(set(HR_FORM_KEYS), {f['key'] for f in HR_FORMS})

    def test_permission_rows_exist_for_every_form(self):
        existing = set(Permission.objects.filter(code__startswith='hr_form_').values_list('code', flat=True))
        self.assertEqual(existing, {hr_form_permission_code(k) for k in HR_FORM_KEYS})

    def test_legacy_user_without_form_permissions_keeps_old_behavior(self):
        user = User.objects.get(pk=self.legacy_user.pk)
        self.assertTrue(hr_form_allowed_for_user(user, 'leave_request'))
        self.assertTrue(hr_form_allowed_for_user(user, 'warning_notice'))

    def test_explicit_form_permission_limits_available_forms(self):
        user = User.objects.get(pk=self.scoped_user.pk)
        self.assertTrue(hr_form_allowed_for_user(user, 'leave_request'))
        self.assertFalse(hr_form_allowed_for_user(user, 'loan_request'))
        self.assertFalse(hr_form_allowed_for_user(user, 'warning_notice'))

    def test_admin_sees_all_forms(self):
        self.assertTrue(all(hr_form_allowed_for_user(self.admin, k) for k in HR_FORM_KEYS))

    def test_index_lists_only_allowed_forms(self):
        self.client.force_login(self.scoped_user)
        response = self.client.get(reverse('web:hr_forms_index'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([f['key'] for f in response.context['forms']], ['leave_request'])

    def test_print_view_blocks_forms_without_permission(self):
        self.client.force_login(self.scoped_user)
        allowed = self.client.get(reverse('web:hr_form_print', args=['leave_request', self.employee.id]))
        blocked = self.client.get(reverse('web:hr_form_print', args=['loan_request', self.employee.id]))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(blocked['Location'], reverse('web:hr_forms_index'))
