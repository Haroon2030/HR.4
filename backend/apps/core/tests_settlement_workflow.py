"""مسار تصفية الموظف: مدير الموارد → أخصائي (تنفيذ) → مدير الموارد (اعتماد نهائي)."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import PendingAction, Role, UserProfile
from apps.core.services import pending_actions as svc
from apps.employees.models import Employee

User = get_user_model()


class SettlementWorkflowTests(TestCase):
    def setUp(self):
        officer_role = Role.objects.create(
            name='Officer WF', role_type=Role.RoleType.HR_OFFICER, is_system_role=True,
        )
        self.requester = User.objects.create_user(username='req', password='x')
        self.gm = User.objects.create_user(username='gm', password='x', is_superuser=True)
        self.officer = User.objects.create_user(username='off', password='x')
        profile = UserProfile.objects.get(user=self.officer)
        profile.role = officer_role
        profile.save(update_fields=['role', 'updated_at'])
        self.officer = User.objects.select_related('profile__role').get(pk=self.officer.pk)
        self.emp = Employee.objects.create(
            name='موظف تصفية', hire_date=date.today() - timedelta(days=400),
        )

    def test_full_chain(self):
        action = svc.submit_settlement_for_approval(
            action_type='terminate', employee=self.emp,
            payload={'end_date': date.today().isoformat(), 'end_reason': 'x'},
            requested_by=self.requester,
        )
        self.assertEqual(action.status, PendingAction.Status.PENDING_GM)
        self.assertFalse(action.executed_at)

        svc.gm_approve_and_assign(action, self.gm, self.officer)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.PENDING_OFFICER)

        svc.officer_approve(action, self.officer)
        action.refresh_from_db()
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.status, Employee.Status.TERMINATED)
        self.assertEqual(action.status, PendingAction.Status.PENDING_GM)
        self.assertTrue(svc.is_settlement_final_stage(action))
        with self.assertRaises(ValueError):
            svc.gm_approve_and_assign(action, self.gm, self.officer)
        with self.assertRaises(ValueError):
            svc.return_action(action, self.gm, 'no')

        svc.gm_final_approve(action, self.gm, 'تم')
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.APPROVED)


class SponsoredSettlementWorkflowTests(TestCase):
    """على كفالة: رفع → تعميد → مدير الموارد → أخصائي → محاسب → مدير الموارد."""

    def setUp(self):
        from apps.setup.models import Sponsorship

        officer_role = Role.objects.create(
            name='Officer WF2', role_type=Role.RoleType.HR_OFFICER, is_system_role=True,
        )
        acct_role = Role.objects.create(
            name='Acct WF', role_type=Role.RoleType.BRANCH_ACCOUNTANT, is_system_role=True,
        )
        self.requester = User.objects.create_user(username='req2', password='x')
        self.gm = User.objects.create_user(username='gm2', password='x', is_superuser=True)
        self.officer = User.objects.create_user(username='off2', password='x')
        self.acct = User.objects.create_user(username='acct2', password='x')
        for user, role in ((self.officer, officer_role), (self.acct, acct_role)):
            profile = UserProfile.objects.get(user=user)
            profile.role = role
            profile.save(update_fields=['role', 'updated_at'])
        self.officer = User.objects.select_related('profile__role').get(pk=self.officer.pk)
        self.acct = User.objects.select_related('profile__role').get(pk=self.acct.pk)
        sp = Sponsorship.objects.create(code='S1', company_name='كفالة')
        self.emp = Employee.objects.create(
            name='موظف كفالة', sponsorship=sp, hire_date=date.today() - timedelta(days=400),
        )

    def test_sponsored_chain(self):
        action = svc.submit_settlement_for_approval(
            action_type='terminate', employee=self.emp,
            payload={'end_date': date.today().isoformat()}, requested_by=self.requester,
        )
        self.assertEqual(action.status, PendingAction.Status.PENDING_BRANCH)

        svc.branch_approve(action, self.requester)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.PENDING_GM)

        svc.gm_approve_and_assign(action, self.gm, self.officer)
        svc.officer_approve(action, self.officer)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.PENDING_ACCOUNTANT)

        svc.accountant_approve(action, self.acct, 'ok')
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.PENDING_GM)
        self.assertTrue(svc.is_settlement_final_stage(action))

        svc.gm_final_approve(action, self.gm)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.APPROVED)


class BranchManagerByRoleRoutingTests(TestCase):
    """مدير فرع مرتبط بفرعه عبر الدور (دون تعيينه في «مدير الفرع») يستلم طلبات فرعه."""

    def test_manager_linked_by_role_receives_branch_requests(self):
        from apps.core.models import Branch, Company
        from apps.core.services.approval_routing import (
            FirstApproverKind, resolve_first_approver, user_can_first_approve,
        )
        from apps.core.web_views.pending_actions import _inbox_for, _user_visible_actions

        company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        branch = Branch.objects.create(name='حائل', code='HAIL', company=company)
        role = Role.objects.create(name='Mgr Hail', role_type=Role.RoleType.MANAGER, is_system_role=True)
        mgr = User.objects.create_user(username='hail_mgr', password='x')
        profile = UserProfile.objects.get(user=mgr)
        profile.role = role
        profile.branch = branch
        profile.save(update_fields=['role', 'branch', 'updated_at'])
        mgr = User.objects.select_related('profile__role').get(pk=mgr.pk)
        submitter = User.objects.create_user(username='hail_entry', password='x')
        emp = Employee.objects.create(name='موظف حائل', branch=branch)

        action = svc.create_pending_action(
            action_type='leave', employee=emp, payload={}, requested_by=submitter,
        )
        decision = resolve_first_approver(action)
        self.assertEqual(decision.kind, FirstApproverKind.BRANCH)
        self.assertEqual(decision.recipient, mgr)
        self.assertTrue(user_can_first_approve(mgr, action))
        self.assertIn(action, _inbox_for(mgr, _user_visible_actions(mgr)))
