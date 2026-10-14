"""صندوق وارد طلبات العمليات: مدير الموارد يرى كل الطلبات كمدير النظام."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Branch, Company, PendingAction, Role
from apps.core.web_views.pending_actions import _inbox_for
from apps.employees.models import Employee

User = get_user_model()


class HRManagerInboxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch1 = Branch.objects.create(name='B1', code='B1', company=company)
        cls.branch2 = Branch.objects.create(name='B2', code='B2', company=company)

        cls.hr_role = Role.objects.create(name='HR Manager', role_type=Role.RoleType.HR_MANAGER)
        cls.hr_manager = User.objects.create_user(username='hrm', password='Pass-User-99!')
        cls.hr_manager.profile.role = cls.hr_role
        cls.hr_manager.profile.branch = cls.branch1
        cls.hr_manager.profile.save()

        cls.superuser = User.objects.create_superuser(username='root', password='Pass-User-99!', email='r@x.com')

        cls.requester = User.objects.create_user(username='req', password='Pass-User-99!')
        cls.emp1 = Employee.objects.create(name='موظف 1', branch=cls.branch1)
        cls.emp2 = Employee.objects.create(name='موظف 2', branch=cls.branch2)

        cls.statuses = {}
        for status in (
            PendingAction.Status.PENDING_BRANCH,
            PendingAction.Status.PENDING_GM,
            PendingAction.Status.PENDING_OFFICER,
            PendingAction.Status.PENDING_ACCOUNTANT,
        ):
            cls.statuses[status] = PendingAction.objects.create(
                action_type='loan_request', employee=cls.emp2,
                branch=cls.branch2, status=status,
                payload={'amount': '100', 'monthly_deduction': '50', 'issued_at': date.today().isoformat()},
                requested_by=cls.requester,
            )

    def _inbox_ids(self, user):
        base = PendingAction.objects.all()
        return set(_inbox_for(user, base).values_list('id', flat=True))

    def test_hr_manager_inbox_contains_every_stage(self):
        ids = self._inbox_ids(User.objects.get(pk=self.hr_manager.pk))
        for status, action in self.statuses.items():
            self.assertIn(action.id, ids, status)

    def test_hr_manager_inbox_matches_superuser_inbox(self):
        hr_ids = self._inbox_ids(User.objects.get(pk=self.hr_manager.pk))
        su_ids = self._inbox_ids(User.objects.get(pk=self.superuser.pk))
        self.assertEqual(hr_ids, su_ids)
