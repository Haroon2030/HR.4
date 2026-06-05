from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Branch, Company, PendingAction
from apps.core.services.approval_routing import (
    TRANSFER_FIRST_APPROVER_LABEL,
    FirstApproverKind,
    approver_display_label,
    first_stage_pending_q,
    first_stage_tab_label,
    resolve_first_approver,
    user_can_first_approve,
)
from apps.core.services.pending_actions import create_pending_action
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


class TransferApprovalRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Xfer Co')
        cls.branch_a = Branch.objects.create(name='Branch A', code='XA', company=cls.company)
        cls.branch_b = Branch.objects.create(name='Branch B', code='XB', company=cls.company)
        cls.branch_mgr = User.objects.create_user(username='xfer_branch_mgr', password='x')
        cls.dept_mgr = User.objects.create_user(username='xfer_dept_mgr', password='x')
        cls.ops_mgr = User.objects.create_user(username='xfer_ops_mgr', password='x')
        cls.requester = User.objects.create_user(username='xfer_requester', password='x')

        cls.branch_a.manager = cls.branch_mgr
        cls.branch_a.save(update_fields=['manager'])

        cls.employee_dept = Administration.objects.create(
            code='DEPT-XF',
            name='قسم الموارد',
            manager=cls.dept_mgr,
        )
        cls.ops_admin = Administration.objects.create(
            code='OPS-XF',
            name='إدارة العمليات',
            manager=cls.ops_mgr,
        )

    def _transfer_action(self, *, branch=None, administration=None):
        employee = Employee.objects.create(
            name='Xfer Emp',
            branch=branch or self.branch_a,
            administration=administration or self.employee_dept,
        )
        return PendingAction.objects.create(
            action_type=PendingAction.ActionType.TRANSFER,
            employee=employee,
            branch=employee.branch,
            administration=self.ops_admin,
            status=PendingAction.Status.PENDING_BRANCH,
            payload={'target_branch_id': self.branch_b.id},
            requested_by=self.requester,
        )

    def test_transfer_routes_to_operations_manager(self):
        action = self._transfer_action()
        decision = resolve_first_approver(action)
        self.assertEqual(decision.kind, FirstApproverKind.ADMINISTRATION)
        self.assertEqual(decision.recipient.id, self.ops_mgr.id)
        self.assertEqual(decision.stage_label, TRANSFER_FIRST_APPROVER_LABEL)

    def test_transfer_not_approved_by_employee_department_manager(self):
        action = self._transfer_action()
        self.assertFalse(user_can_first_approve(self.dept_mgr, action))
        self.assertFalse(user_can_first_approve(self.branch_mgr, action))

    def test_transfer_approved_only_by_operations_manager(self):
        action = self._transfer_action()
        self.assertTrue(user_can_first_approve(self.ops_mgr, action))

    def test_create_pending_action_sets_operations_administration(self):
        employee = Employee.objects.create(
            name='Xfer Create',
            branch=self.branch_a,
            administration=self.employee_dept,
        )
        action = create_pending_action(
            action_type=PendingAction.ActionType.TRANSFER,
            employee=employee,
            payload={'target_branch_id': self.branch_b.id},
            requested_by=self.requester,
        )
        self.assertEqual(action.administration_id, self.ops_admin.id)

    def test_ops_manager_inbox_includes_all_transfers(self):
        action_a = self._transfer_action(branch=self.branch_a)
        action_b = self._transfer_action(branch=self.branch_b)
        q = first_stage_pending_q(
            self.ops_mgr,
            model_status_pending_branch=PendingAction.Status.PENDING_BRANCH,
            supports_transfer=True,
        )
        visible = PendingAction.objects.filter(q)
        self.assertIn(action_a.id, list(visible.values_list('id', flat=True)))
        self.assertIn(action_b.id, list(visible.values_list('id', flat=True)))

    def test_branch_manager_inbox_excludes_transfers(self):
        action = self._transfer_action(branch=self.branch_a)
        q = first_stage_pending_q(
            self.branch_mgr,
            model_status_pending_branch=PendingAction.Status.PENDING_BRANCH,
            supports_transfer=True,
        )
        visible = PendingAction.objects.filter(q)
        self.assertNotIn(action.id, list(visible.values_list('id', flat=True)))
