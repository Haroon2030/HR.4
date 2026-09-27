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

    def _build_hire_request(self, *, with_admin: bool):
        from apps.employees.models import EmploymentRequest

        return EmploymentRequest.objects.create(
            name='Hire',
            branch=self.branch,
            administration=self.administration if with_admin else None,
            status=EmploymentRequest.Status.PENDING_BRANCH,
        )

    def test_first_stage_q_on_hire_requests_routes_by_administration(self):
        from apps.core.services.approval_routing import first_stage_pending_q
        from apps.employees.models import EmploymentRequest

        admin_req = self._build_hire_request(with_admin=True)
        branch_req = self._build_hire_request(with_admin=False)

        def inbox_ids(user):
            q = first_stage_pending_q(
                user,
                model=EmploymentRequest,
                model_status_pending_branch=EmploymentRequest.Status.PENDING_BRANCH,
            )
            return set(EmploymentRequest.objects.filter(q).values_list('id', flat=True))

        self.assertEqual(inbox_ids(self.admin_manager), {admin_req.id})
        self.assertEqual(inbox_ids(self.branch_manager), {branch_req.id})

    def test_first_stage_q_on_pending_actions_excludes_cash_shortage_for_admin_manager(self):
        from apps.core.services.approval_routing import first_stage_pending_q

        leave = self._build_action(with_admin=True)
        shortage = PendingAction.objects.create(
            action_type=PendingAction.ActionType.CASH_SHORTAGE,
            employee=leave.employee,
            branch=self.branch,
            administration=self.administration,
            status=PendingAction.Status.PENDING_BRANCH,
        )
        q = first_stage_pending_q(
            self.admin_manager,
            model=PendingAction,
            model_status_pending_branch=PendingAction.Status.PENDING_BRANCH,
        )
        ids = set(PendingAction.objects.filter(q).values_list('id', flat=True))
        self.assertIn(leave.id, ids)
        self.assertNotIn(shortage.id, ids)

    def test_dashboard_loads_for_administration_manager_with_pending_hire(self):
        from django.urls import reverse

        req = self._build_hire_request(with_admin=True)
        self.client.force_login(self.admin_manager)
        response = self.client.get(reverse('web:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(req, list(response.context['pending_requests']))

    def _grant_admin_approval_permission(self, user):
        from apps.core.models import AppModule, Permission

        module, _ = AppModule.objects.get_or_create(
            code='operations',
            defaults={'name': 'operations', 'icon': 'circle', 'order': 50},
        )
        perm, _ = Permission.objects.get_or_create(
            code='operations.approve_admin',
            defaults={
                'module': module,
                'operation': Permission.Operation.APPROVE_ADMINISTRATION,
                'name': 'operations.approve_admin',
            },
        )
        role = Role.objects.create(name='مدير إدارة', role_type=Role.RoleType.ADMIN_MANAGER)
        role.permissions.add(perm)
        profile = user.profile
        profile.role = role
        profile.save(update_fields=['role'])

    def test_employment_list_shows_pending_hire_to_administration_manager(self):
        from django.urls import reverse

        other_admin = Administration.objects.create(
            code='ADM-OTHER', name='Other', manager=self.other_manager,
        )
        own_req = self._build_hire_request(with_admin=True)
        other_req = self._build_hire_request(with_admin=False)
        other_req.administration = other_admin
        other_req.save(update_fields=['administration'])

        self._grant_admin_approval_permission(self.admin_manager)
        self.assertFalse(self.admin_manager.managed_branches.exists())

        self.client.force_login(self.admin_manager)
        response = self.client.get(reverse('web:list_employment_requests'))

        self.assertEqual(response.status_code, 200)
        rows = {r.id: r for r in response.context['requests']}
        self.assertIn(own_req.id, rows)
        self.assertNotIn(other_req.id, rows)
        self.assertTrue(rows[own_req.id].can_first_approve)

    def test_administration_manager_can_approve_hire_from_list(self):
        from django.urls import reverse
        from apps.employees.models import EmploymentRequest

        req = self._build_hire_request(with_admin=True)
        self._grant_admin_approval_permission(self.admin_manager)

        self.client.force_login(self.admin_manager)
        self.client.post(reverse('web:approve_employment_request', args=[req.id]))

        req.refresh_from_db()
        self.assertEqual(req.status, EmploymentRequest.Status.PENDING_GM)

    def test_stage_label_strips_technical_role_code(self):
        from apps.core.models import UserProfile

        role = Role.objects.create(
            name='BRANCH_MANAGER — مدير الفرع',
            role_type=Role.RoleType.MANAGER,
        )
        UserProfile.objects.filter(user=self.branch_manager).update(role=role)
        action = self._build_action(with_admin=False)
        decision = resolve_first_approver(action)
        self.assertEqual(decision.stage_label, 'مدير الفرع')
        self.assertEqual(approver_display_label(self.branch_manager), 'مدير الفرع')
