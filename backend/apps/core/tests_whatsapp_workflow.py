"""Tests for WhatsApp workflow approval notifications."""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.core.models import Branch, Company, PendingAction, Role, UserProfile, WhatsAppMessageLog
from apps.core.services.employment_requests import (
    branch_approve as er_branch_approve,
    gm_approve_and_assign as er_gm_assign,
    notify_branch_on_create as er_notify_create,
)
from apps.core.services.pending_actions import (
    branch_approve,
    create_pending_action,
    gm_approve_and_assign,
    notify_branch_on_create,
)
from apps.employees.models import Employee, EmploymentRequest
from apps.setup.models import Administration, EvolutionWhatsAppSettings, WorkflowWhatsAppSettings

User = get_user_model()


@override_settings(
    WHATSAPP_ENABLED=True,
    EVOLUTION_API_URL='http://evolution.test:8081',
    EVOLUTION_API_KEY='test-key',
    EVOLUTION_INSTANCE='hr',
    ALLOWED_HOSTS=['testserver'],
)
class WhatsAppWorkflowNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='WA Co')
        cls.branch = Branch.objects.create(name='Main', code='WA1', company=cls.company)
        cls.administration = Administration.objects.create(
            code='ADM-WA',
            name='Ops',
        )

        cls.requester = User.objects.create_user(username='req_user', password='x')
        cls.branch_manager = User.objects.create_user(username='branch_mgr', password='x')
        cls.admin_manager = User.objects.create_user(username='admin_mgr', password='x')
        cls.hr_officer = User.objects.create_user(username='hr_off', password='x')
        cls.accountant = User.objects.create_user(username='acct', password='x')

        cls.branch.manager = cls.branch_manager
        cls.branch.save(update_fields=['manager'])
        cls.administration.manager = cls.admin_manager
        cls.administration.save(update_fields=['manager'])

        cls.officer_role = Role.objects.filter(role_type=Role.RoleType.HR_OFFICER).first()
        if not cls.officer_role:
            cls.officer_role = Role.objects.create(name='أخصائي', role_type=Role.RoleType.HR_OFFICER)
        cls.acct_role = Role.objects.filter(role_type=Role.RoleType.BRANCH_ACCOUNTANT).first()
        if not cls.acct_role:
            cls.acct_role = Role.objects.create(name='محاسب', role_type=Role.RoleType.BRANCH_ACCOUNTANT)

        UserProfile.objects.filter(user=cls.branch_manager).update(phone='0511111111')
        UserProfile.objects.filter(user=cls.admin_manager).update(phone='0522222222')
        UserProfile.objects.filter(user=cls.hr_officer).update(phone='0533333333')
        UserProfile.objects.filter(user=cls.accountant).update(
            phone='0544444444',
            role=cls.acct_role,
            branch=cls.branch,
        )
        UserProfile.objects.filter(user=cls.hr_officer).update(role=cls.officer_role)

        cls.employee = Employee.objects.create(
            name='Test Employee',
            branch=cls.branch,
            administration=cls.administration,
        )

        wf = WorkflowWhatsAppSettings.get_solo()
        wf.is_enabled = True
        wf.recipient_phones = {
            'system_admin': '0555555555',
            'hr_manager': '0566666666',
        }
        wf.save()

        evo = EvolutionWhatsAppSettings.get_solo()
        evo.is_enabled = True
        evo.api_url = 'http://evolution.test:8081'
        evo.api_key = 'test-key'
        evo.instance_name = 'hr'
        evo.save()

    def setUp(self):
        self._send_patch = patch(
            'apps.core.services.whatsapp.client.send_text',
            return_value={'ok': True},
        )
        self._configured_patch = patch(
            'apps.core.services.whatsapp.client.is_configured',
            return_value=True,
        )
        self.mock_send = self._send_patch.start()
        self._configured_patch.start()
        WhatsAppMessageLog.objects.all().delete()
        self.hr_officer = User.objects.select_related('profile__role').get(pk=self.hr_officer.pk)
        self.branch_manager = User.objects.select_related('profile__role').get(pk=self.branch_manager.pk)
        self.admin_manager = User.objects.select_related('profile__role').get(pk=self.admin_manager.pk)
        self.accountant = User.objects.select_related('profile__role').get(pk=self.accountant.pk)

    def tearDown(self):
        self._send_patch.stop()
        self._configured_patch.stop()

    def _create_leave_action(self, *, with_admin=True):
        employee = self.employee
        if not with_admin:
            employee.administration = None
            employee.save(update_fields=['administration'])
        return create_pending_action(
            action_type=PendingAction.ActionType.LEAVE,
            employee=employee,
            payload={'start_date': '2026-01-01', 'end_date': '2026-01-05'},
            requested_by=self.requester,
        )

    def test_create_pending_action_sends_broadcast_and_first_stage(self):
        action = self._create_leave_action()
        # signal + notify_branch_on_create: broadcast 2 + admin manager 1
        phones = {call.kwargs.get('phone') or call.args[0] for call in self.mock_send.call_args_list}
        self.assertIn('966555555555', phones)
        self.assertIn('966566666666', phones)
        self.assertIn('966522222222', phones)
        self.assertTrue(
            WhatsAppMessageLog.objects.filter(
                event_type='workflow.pending_action.created.broadcast',
                related_action=action,
            ).exists()
        )

    def test_branch_approve_sends_hr_manager_whatsapp(self):
        action = self._create_leave_action()
        self.mock_send.reset_mock()
        branch_approve(action, self.admin_manager, notes='ok')
        phones = {c.kwargs.get('phone') for c in self.mock_send.call_args_list}
        self.assertIn('966566666666', phones)
        self.assertTrue(
            WhatsAppMessageLog.objects.filter(event_type='workflow.pending_action.pending_gm').exists()
        )

    def test_gm_assign_sends_officer_whatsapp(self):
        action = self._create_leave_action()
        branch_approve(action, self.admin_manager)
        self.mock_send.reset_mock()
        gm_approve_and_assign(action, self.requester, self.hr_officer)
        phones = {c.kwargs.get('phone') for c in self.mock_send.call_args_list}
        self.assertIn('966533333333', phones)
        self.assertTrue(
            WhatsAppMessageLog.objects.filter(
                event_type='workflow.pending_action.officer_assigned',
                recipient_user=self.hr_officer,
            ).exists()
        )

    def test_cash_shortage_notifies_accountant_with_attachment_hint(self):
        doc = SimpleUploadedFile('shortage.pdf', b'%PDF-1.4', content_type='application/pdf')
        self.mock_send.reset_mock()
        action = create_pending_action(
            action_type=PendingAction.ActionType.CASH_SHORTAGE,
            employee=self.employee,
            payload={'amount': '100', 'shortage_date': '2026-06-01'},
            requested_by=self.requester,
            attachment=doc,
        )
        phones = {c.kwargs.get('phone') for c in self.mock_send.call_args_list}
        self.assertIn('966544444444', phones)
        log = WhatsAppMessageLog.objects.filter(
            event_type='workflow.pending_action.first_stage.accountant',
        ).first()
        self.assertIsNotNone(log)
        self.assertIn('مستند العجز', log.message)

    def test_disabled_settings_skips_send(self):
        wf = WorkflowWhatsAppSettings.get_solo()
        wf.is_enabled = False
        wf.save()
        self.mock_send.reset_mock()
        from apps.core.services.whatsapp import workflow_notifier

        action = self._create_leave_action()
        workflow_notifier.notify_whatsapp_request_created(action)
        self.mock_send.assert_not_called()

    def test_missing_phone_logs_skipped(self):
        UserProfile.objects.filter(user=self.hr_officer).update(phone='')
        action = self._create_leave_action()
        branch_approve(action, self.admin_manager)
        self.mock_send.reset_mock()
        gm_approve_and_assign(action, self.requester, self.hr_officer)
        skipped = WhatsAppMessageLog.objects.filter(
            event_type='workflow.pending_action.officer_assigned',
            status=WhatsAppMessageLog.Status.SKIPPED,
        )
        self.assertEqual(skipped.count(), 1)

    def test_employment_request_create_and_gm_flow(self):
        req = EmploymentRequest.objects.create(
            name='New Hire',
            branch=self.branch,
            administration=None,
            requested_by=self.requester,
            status=EmploymentRequest.Status.PENDING_BRANCH,
        )
        self.mock_send.reset_mock()
        er_notify_create(req)
        phones = {c.kwargs.get('phone') for c in self.mock_send.call_args_list}
        self.assertIn('966555555555', phones)
        self.assertIn('966511111111', phones)

        self.mock_send.reset_mock()
        er_branch_approve(req, self.branch_manager)
        phones = {c.kwargs.get('phone') for c in self.mock_send.call_args_list}
        self.assertIn('966566666666', phones)

        self.mock_send.reset_mock()
        er_gm_assign(req, self.requester, self.hr_officer)
        phones = {c.kwargs.get('phone') for c in self.mock_send.call_args_list}
        self.assertIn('966533333333', phones)
