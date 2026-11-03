"""زر «الإضافة السريعة» في ملف الموظف يتبع صلاحية employees.quick_add."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Branch, Company, Permission, Role
from apps.employees.models import Employee

User = get_user_model()
BUTTON = 'إضافة سريعة'


class QuickAddPermissionTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', code='QA1', company=company)
        self.employee = Employee.objects.create(
            name='موظف', branch=branch, status=Employee.Status.ACTIVE, basic_salary=Decimal('3000'),
        )

    def _page(self, codes):
        user = User.objects.create_user(f'qa{len(codes)}{abs(hash(tuple(codes))) % 999}', password='x')
        role = Role.objects.create(name=f'دور {user.username}', role_type=Role.RoleType.HR_OFFICER)
        role.permissions.add(*Permission.objects.filter(code__in=codes))
        user.profile.role = role
        user.profile.branch = self.employee.branch
        user.profile.save(update_fields=['role', 'branch'])
        self.client.force_login(user)
        return self.client.get(reverse('web:view_employee', args=[self.employee.id])).content.decode()

    def test_hidden_without_permission_even_with_edit(self):
        self.assertNotIn(BUTTON, self._page(['employees.view', 'employees.edit']))

    def test_shown_with_permission(self):
        self.assertIn(BUTTON, self._page(['employees.view', 'employees.quick_add']))
