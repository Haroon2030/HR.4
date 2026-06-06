from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Branch, Company, PendingAction
from apps.core.services.approval_routing import (
    FirstApproverKind,
    approver_display_label,
    first_stage_tab_label,
    resolve_first_approver,
    user_can_first_approve,
)
from apps.core.models import Role
from apps.employees.models import Employee
from apps.setup.models import Administration

User = get_user_model()


class ApprovalRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Route Co')
        cls.branch = Branch.objects.create(name='Main', code='RT1', company=cls.company)
        cls.branch_manager = User.objects.create_user(username='branch_mgr', password='x')
        cls.admin_manager = User.objects.create_user(username='admin_mgr', password='x')
        cls.other_manager = User.objects.create_user(username='other_mgr', password='x')
        cls.branch.manager = cls.branch_manager
        cls.branch.save(update_fields=['manager'])

        cls.administration = Administration.objects.create(
            code='ADM-RT',
            name='Operations',
            manager=cls.admin_manager,
        )

    def _build_action(self, *, with_admin: bool):
        employee = Employee.objects.create(
            name='Emp',
            branch=self.branch,
            administration=self.administration if with_admin else None,
        )
        return PendingAction.objects.create(
            action_type=PendingAction.ActionType.LEAVE,
            employee=employee,
            branch=employee.branch,
            administration=employee.administration,
            status=PendingAction.Status.PENDING_BRANCH,
        )

    def test_prefers_administration_manager_when_exists(self):
        action = self._build_action(with_admin=True)
        decision = resolve_first_approver(action)
        self.assertEqual(decision.kind, FirstApproverKind.ADMINISTRATION)
        self.assertEqual(decision.recipient.id, self.admin_manager.id)

    def test_falls_back_to_branch_manager_without_administration(self):
        action = self._build_action(with_admin=False)
        decision = resolve_first_approver(action)
        self.assertEqual(decision.kind, FirstApproverKind.BRANCH)
        self.assertEqual(decision.recipient.id, self.branch_manager.id)

    def test_user_can_first_approve_matches_routing(self):
        action = self._build_action(with_admin=True)
        self.assertTrue(user_can_first_approve(self.admin_manager, action))
        self.assertFalse(user_can_first_approve(self.branch_manager, action))
        self.assertFalse(user_can_first_approve(self.other_manager, action))

    def test_stage_label_uses_approver_role_name(self):
        from apps.core.models import UserProfile

        role = Role.objects.create(
            name='المدير المالي',
            role_type=Role.RoleType.ADMIN_MANAGER,
        )
        UserProfile.objects.filter(user=self.admin_manager).update(role=role)
        action = self._build_action(with_admin=True)
        decision = resolve_first_approver(action)
        self.assertEqual(decision.stage_label, 'المدير المالي')
        self.assertEqual(first_stage_tab_label(self.admin_manager), 'المدير المالي')
