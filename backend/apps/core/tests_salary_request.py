"""صلاحية «تقديم طلب تعديل راتب» لموظف الرفع من الإضافة السريعة."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.core.models import Branch, Company, PendingAction, Permission, Role, UserProfile
from apps.core.salary_access import user_can_edit_salary, user_can_request_salary_adjust
from apps.employees.models import Employee

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class SalaryAdjustRequestPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة')
        cls.branch = Branch.objects.create(name='فرع', code='SR1', company=company)
        cls.employee = Employee.objects.create(
            name='موظف', branch=cls.branch, status=Employee.Status.ACTIVE,
            basic_salary=Decimal('3000'),
        )
        role = Role.objects.create(name='موظف رفع اختبار', role_type=Role.RoleType.SPECIALIST)
        cls.user = User.objects.create_user(username='uploader', password='x12345678')
        profile, _ = UserProfile.objects.get_or_create(user=cls.user)
        profile.role = role
        profile.branch = cls.branch
        profile.save(update_fields=['role', 'branch'])
        cls.role = role
        for code in ('employees.view', 'employees.edit'):
            role.permissions.add(Permission.objects.get(code=code))

    def _user(self):
        return User.objects.select_related('profile__role').get(pk=self.user.pk)

    def test_without_permission_cannot_request(self):
        self.assertFalse(user_can_request_salary_adjust(self._user()))
        client = Client()
        client.force_login(self._user())
        response = client.get(reverse('web:view_employee', args=[self.employee.pk]))
        self.assertNotContains(response, "quickModal='salary'")

    def test_request_permission_allows_request_without_edit_salary(self):
        perm, _ = Permission.objects.get_or_create(
            code='employees.request_salary_adjust',
            defaults={
                'module': Permission.objects.get(code='employees.edit').module,
                'operation': 'request_salary_adjust',
                'name': 'تقديم طلب تعديل راتب',
            },
        )
        self.role.permissions.add(perm)
        user = self._user()
        self.assertFalse(user_can_edit_salary(user))
        self.assertTrue(user_can_request_salary_adjust(user))

        client = Client()
        client.force_login(user)
        page = client.get(reverse('web:view_employee', args=[self.employee.pk]))
        self.assertContains(page, "quickModal='salary'")
        self.assertNotContains(page, 'raise_amount')  # لا يرى هيكل الراتب الحالي

        client.post(reverse('web:adjust_employee_salary', args=[self.employee.pk]), {
            'new_basic_salary': '3500',
            'effective_date': '2026-10-18',
            'reason': 'مكافأة',
        })
        action = PendingAction.objects.get(action_type='salary_adjust', employee=self.employee)
        self.assertEqual(Decimal(action.payload['new_basic_salary']), Decimal('3500'))
