"""دور «موظف الرفع»: بلا تصدير/استيراد الموظفين وبلا زر «تعديل / إكمال البيانات»."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Branch, Company, Permission, Role, UserProfile
from apps.employees.models import Employee

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class UploadRoleButtonsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة')
        cls.branch = Branch.objects.create(name='فرع', code='BR-U', company=company)
        base = list(Permission.objects.filter(code__in=['employees.view', 'employees.add', 'employees.edit']))
        cls.upload_role = Role.objects.create(name='موظف رفع ت', role_type=Role.RoleType.SPECIALIST)
        cls.upload_role.permissions.add(*base)
        cls.officer_role = Role.objects.create(name='منفذ ت', role_type=Role.RoleType.HR_OFFICER)
        cls.officer_role.permissions.add(
            *base,
            *Permission.objects.filter(
                code__in=['employees.export', 'employees.import', 'employees.edit_profile'],
            ),
        )
        cls.employee = Employee.objects.create(
            name='موظف', branch=cls.branch, status=Employee.Status.ACTIVE, basic_salary=Decimal('3000'),
        )

    def _login(self, username, role):
        user = User.objects.create_user(username=username, password='x12345678')
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.branch = self.branch
        profile.save(update_fields=['role', 'branch'])
        self.client.force_login(User.objects.select_related('profile__role').get(pk=user.pk))

    def _page(self, url):
        r = self.client.get(url)
        from django.contrib.messages import get_messages
        self.assertEqual(r.status_code, 200, (r.get('Location'), [str(m) for m in get_messages(r.wsgi_request)]))
        return r.content.decode()

    def test_new_permissions_exist(self):
        codes = set(Permission.objects.filter(
            code__in=['employees.export', 'employees.import', 'employees.edit_profile'],
        ).values_list('code', flat=True))
        self.assertEqual(codes, {'employees.export', 'employees.import', 'employees.edit_profile'})

    def test_upload_role_list_has_no_export_import(self):
        self._login('up', self.upload_role)
        html = self._page(reverse('web:list_employees'))
        self.assertNotIn('id="ns-export-link"', html)
        self.assertNotIn('id="ns-import-form"', html)

    def test_upload_role_cannot_call_export_or_import(self):
        self._login('up', self.upload_role)
        r = self.client.get(reverse('web:export_non_sponsored_employees_excel'))
        self.assertNotEqual(r.get('Content-Type', ''), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        r = self.client.post(reverse('web:import_sponsored_employees_excel'))
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('import', r['Location'])

    def test_upload_role_view_has_no_edit_button(self):
        self._login('up', self.upload_role)
        html = self._page(reverse('web:view_employee', args=[self.employee.id]))
        self.assertNotIn(reverse('web:edit_employee', args=[self.employee.id]) + '"', html)

    def test_role_with_new_permissions_keeps_buttons(self):
        self._login('off', self.officer_role)
        html = self._page(reverse('web:list_employees'))
        self.assertIn('id="ns-export-link"', html)
        self.assertIn('id="ns-import-form"', html)
        html = self._page(reverse('web:view_employee', args=[self.employee.id]))
        self.assertIn(reverse('web:edit_employee', args=[self.employee.id]) + '"', html)
