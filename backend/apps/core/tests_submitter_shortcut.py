"""رفع الأخصائي يذهب مباشرة لمدير الموارد، ورفع الموارد البشرية يُعمَّد تلقائياً باسم مقدّمه."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Branch, Company, PendingAction, Role
from apps.core.services import employment_requests as er
from apps.core.services.pending_actions import create_pending_action, resubmit_action
from apps.employees.models import Employee, EmploymentRequest

User = get_user_model()


class SubmitterShortcutTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة')
        self.branch = Branch.objects.create(name='فرع', code='SC1', company=company)
        # مدير فرع فعّال: بدون الاختصار كان الطلب سيبقى عنده
        self.manager = self._user('sc_mgr', Role.RoleType.MANAGER)
        self.branch.manager = self.manager
        self.branch.save()
        self.emp = Employee.objects.create(
            name='موظف', employee_number='900', branch=self.branch, basic_salary=Decimal('3000'),
        )

    def _user(self, username, role_type):
        user = User.objects.create_user(username, password='x')
        role = Role.objects.create(name=f'دور {username}', role_type=role_type)
        profile = user.profile
        profile.role = role
        profile.branch = self.branch
        profile.save(update_fields=['role', 'branch'])
        return user

    def _action(self, user):
        return create_pending_action(
            action_type='leave', employee=self.emp, payload={'days': '1'}, requested_by=user,
        )

    def test_specialist_goes_straight_to_hr_manager(self):
        action = self._action(self._user('sc_spec', Role.RoleType.SPECIALIST))
        self.assertEqual(action.status, PendingAction.Status.PENDING_GM)
        self.assertIsNone(action.branch_reviewed_by)

    def test_hr_submission_is_auto_endorsed_by_submitter(self):
        for role_type in (Role.RoleType.HR_OFFICER, Role.RoleType.HR_MANAGER):
            user = self._user(f'sc_{role_type}', role_type)
            action = self._action(user)
            self.assertEqual(action.status, PendingAction.Status.PENDING_GM)
            self.assertEqual(action.branch_reviewed_by, user)
            self.assertIsNotNone(action.branch_reviewed_at)

    def test_other_roles_keep_normal_first_stage(self):
        action = self._action(self._user('sc_acc', Role.RoleType.BRANCH_ACCOUNTANT))
        self.assertEqual(action.status, PendingAction.Status.PENDING_BRANCH)

    def test_cash_shortage_is_not_shortcut(self):
        action = create_pending_action(
            action_type='cash_shortage', employee=self.emp, payload={},
            requested_by=self._user('sc_spec2', Role.RoleType.SPECIALIST),
        )
        self.assertEqual(action.status, PendingAction.Status.PENDING_BRANCH)

    def test_resubmit_by_specialist_skips_first_stage_again(self):
        user = self._user('sc_spec3', Role.RoleType.SPECIALIST)
        action = self._action(user)
        PendingAction.objects.filter(pk=action.pk).update(status=PendingAction.Status.RETURNED)
        action.refresh_from_db()
        resubmit_action(action, user)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.PENDING_GM)

    def test_employment_request_by_specialist_and_hr(self):
        spec = self._user('sc_spec4', Role.RoleType.SPECIALIST)
        hr = self._user('sc_hr4', Role.RoleType.HR_OFFICER)
        acc = self._user('sc_acc4', Role.RoleType.BRANCH_ACCOUNTANT)
        results = {}
        for key, user in (('spec', spec), ('hr', hr), ('acc', acc)):
            req = EmploymentRequest.objects.create(
                name=f'مرشح {key}', branch=self.branch, requested_by=user, basic_salary=3000,
            )
            er.skip_first_stage_if_unrouted(req)
            req.refresh_from_db()
            results[key] = req
        self.assertEqual(results['spec'].status, EmploymentRequest.Status.PENDING_GM)
        self.assertEqual(results['hr'].status, EmploymentRequest.Status.PENDING_GM)
        self.assertEqual(results['hr'].branch_reviewed_by, hr)
        self.assertEqual(results['acc'].status, EmploymentRequest.Status.PENDING_BRANCH)
