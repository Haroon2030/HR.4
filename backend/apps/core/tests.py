"""اختبارات لـ apps.core.services.pending_actions executors."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import Branch, Company, PendingAction, Role
from apps.core.services.pending_actions import (
    create_pending_action,
    execute_pending_action,
    revert_employee_settlement_pending_status,
)
from apps.employees.models import (
    Employee,
    EmployeeAbsence,
    EmployeeLeave,
    EmployeeLoan,
    EmployeeStatement,
)
from apps.setup.models import Sponsorship

User = get_user_model()


class _BaseExecutorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة اختبار')
        cls.branch_a = Branch.objects.create(name='فرع A', code='BR-A', company=cls.company)
        cls.branch_b = Branch.objects.create(name='فرع B', code='BR-B', company=cls.company)
        cls.requester = User.objects.create_user(
            username='specialist', password='x', is_staff=True
        )
        cls.approver = User.objects.create_user(
            username='manager', password='x', is_staff=True
        )
        cls.sponsorship = Sponsorship.objects.create(
            code='SP-EXEC-TEST',
            company_name='كفالة اختبار',
        )

    def setUp(self):
        self.employee = Employee.objects.create(
            name='موظف اختبار',
            branch=self.branch_a,
            status=Employee.Status.ACTIVE,
            hire_date=date(2024, 1, 1),
            basic_salary=Decimal('3000'),
            housing_allowance=Decimal('500'),
            transport_allowance=Decimal('200'),
            available_leave_balance=Decimal('5'),
            sponsorship=self.sponsorship,
        )

    def _make_action(self, action_type, payload):
        return PendingAction.objects.create(
            action_type=action_type,
            employee=self.employee,
            branch=self.branch_a,
            payload=payload,
            requested_by=self.requester,
            status=PendingAction.Status.APPROVED,
        )


class LeaveExecutorTests(_BaseExecutorTests):
    def test_annual_leave_increases_balance_and_creates_record(self):
        action = self._make_action('leave', {
            'leave_type': EmployeeLeave.LeaveType.ANNUAL,
            'date_from': '2025-02-01',
            'date_to': '2025-02-05',
            'days': 5,
            'notes': 'إجازة سنوية',
        })

        msg = execute_pending_action(action, self.approver)

        self.assertIn('5', msg)
        self.assertEqual(EmployeeLeave.objects.filter(employee=self.employee).count(), 1)

        leave = EmployeeLeave.objects.get(employee=self.employee)
        self.assertEqual(leave.days, Decimal('5'))
        self.assertEqual(leave.leave_type, EmployeeLeave.LeaveType.ANNUAL)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.available_leave_balance, Decimal('10'))

        action.refresh_from_db()
        self.assertIsNotNone(action.executed_at)
        self.assertEqual(action.execution_error, '')

    def test_non_annual_leave_does_not_change_balance(self):
        action = self._make_action('leave', {
            'leave_type': EmployeeLeave.LeaveType.SICK,
            'date_from': '2025-02-01',
            'date_to': '2025-02-03',
            'days': 3,
        })
        execute_pending_action(action, self.approver)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.available_leave_balance, Decimal('5'))


class LeaveAnnualWithoutSponsorshipTests(TestCase):
    """الإجازة السنوية تتطلب كفالة — رفض واضح عند غيابها."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة كفالة')
        cls.branch = Branch.objects.create(name='فرع ك', code='BR-K', company=cls.company)
        cls.requester = User.objects.create_user(username='sp_k', password='x', is_staff=True)
        cls.approver = User.objects.create_user(username='mg_k', password='x', is_staff=True)

    def test_annual_leave_raises_without_sponsorship(self):
        emp = Employee.objects.create(
            name='بدون كفالة',
            branch=self.branch,
            status=Employee.Status.ACTIVE,
            hire_date=date(2024, 1, 1),
            basic_salary=Decimal('3000'),
            sponsorship=None,
            available_leave_balance=Decimal('0'),
        )
        action = PendingAction.objects.create(
            action_type='leave',
            employee=emp,
            branch=self.branch,
            payload={
                'leave_type': EmployeeLeave.LeaveType.ANNUAL,
                'date_from': '2025-02-01',
                'date_to': '2025-02-03',
                'days': 3,
            },
            requested_by=self.requester,
            status=PendingAction.Status.APPROVED,
        )
        with self.assertRaises(ValueError) as ctx:
            execute_pending_action(action, self.approver)
        self.assertIn('كفالة', str(ctx.exception))


class PendingActionIdempotencyTests(_BaseExecutorTests):
    def test_execute_twice_raises(self):
        action = self._make_action('absence', {
            'absence_date': '2025-06-10',
            'days': 1,
            'reason': 'اختبار',
        })
        execute_pending_action(action, self.approver)
        action.refresh_from_db()
        self.assertIsNotNone(action.executed_at)
        with self.assertRaises(ValueError) as ctx:
            execute_pending_action(action, self.approver)
        self.assertIn('مسبقاً', str(ctx.exception))


class LoanRequestExecutorTests(_BaseExecutorTests):
    def test_creates_loan_and_installments(self):
        action = self._make_action('loan_request', {
            'amount': '5000',
            'monthly_deduction': '1000',
            'installments': 3,
            'issued_at': '2025-06-01',
            'first_deduction_date': '2025-07-01',
            'reason': 'ظرف طارئ',
        })
        msg = execute_pending_action(action, self.approver)
        self.assertIn('5000', msg)
        loan = EmployeeLoan.objects.get(employee=self.employee)
        self.assertEqual(loan.installments_log.count(), 3)


class AbsenceExecutorTests(_BaseExecutorTests):
    def test_registers_absence_with_deduction(self):
        action = self._make_action('absence', {
            'absence_date': '2025-06-15',
            'days': 2,
            'reason': 'مرض',
        })
        execute_pending_action(action, self.approver)
        ab = EmployeeAbsence.objects.get(employee=self.employee)
        self.assertEqual(ab.days, 2)
        self.assertGreater(ab.deduction_amount, 0)


class TerminateExecutorTests(_BaseExecutorTests):
    def test_terminate_sets_status_and_creates_statement(self):
        action = self._make_action('terminate', {
            'end_date': '2025-03-01',
            'end_reason': 'استقالة',
        })
        execute_pending_action(action, self.approver)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.TERMINATED)
        self.assertEqual(self.employee.end_date, date(2025, 3, 1))
        self.assertEqual(self.employee.end_reason, 'استقالة')

        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        )
        self.assertIn('استقالة', st.content)

    def test_terminate_removes_employee_from_draft_payroll(self):
        from apps.payroll.models import PayrollLine, PayrollRun
        from apps.payroll.services.engine import build_payroll_run

        run = build_payroll_run(
            self.branch_a, 2025, 6, user=self.approver,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.pk,
        )
        self.assertTrue(
            PayrollLine.objects.filter(run=run, employee=self.employee).exists(),
        )

        action = self._make_action('terminate', {
            'end_date': '2025-06-15',
            'end_reason': 'تصفية',
        })
        execute_pending_action(action, self.approver)

        self.assertFalse(
            PayrollLine.objects.filter(run=run, employee=self.employee).exists(),
        )
        self.assertEqual(run.status, PayrollRun.Status.DRAFT)


class SettlementPendingStatusTests(_BaseExecutorTests):
    def test_create_end_of_service_marks_employee_suspended(self):
        action = create_pending_action(
            action_type='end_of_service',
            employee=self.employee,
            payload={
                'end_date': '2026-06-01',
                'terminated_by': 'company',
            },
            requested_by=self.requester,
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)
        self.assertEqual(action.payload['status_before_settlement'], Employee.Status.ACTIVE)

    def test_create_terminate_marks_employee_suspended(self):
        create_pending_action(
            action_type='terminate',
            employee=self.employee,
            payload={
                'end_date': '2026-06-01',
                'end_reason': 'تصفية',
            },
            requested_by=self.requester,
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)

    def test_duplicate_open_settlement_raises(self):
        create_pending_action(
            action_type='end_of_service',
            employee=self.employee,
            payload={'end_date': '2026-06-01', 'terminated_by': 'company'},
            requested_by=self.requester,
        )
        with self.assertRaises(ValueError):
            create_pending_action(
                action_type='terminate',
                employee=self.employee,
                payload={'end_date': '2026-06-02', 'end_reason': 'x'},
                requested_by=self.requester,
            )

    def test_revert_restores_previous_status_on_delete(self):
        action = create_pending_action(
            action_type='terminate',
            employee=self.employee,
            payload={'end_date': '2026-06-01', 'end_reason': 'تصفية'},
            requested_by=self.requester,
        )
        revert_employee_settlement_pending_status(action)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)

    def test_execute_end_of_service_sets_terminated_after_suspended(self):
        action = create_pending_action(
            action_type='end_of_service',
            employee=self.employee,
            payload={
                'end_date': '2026-05-01',
                'terminated_by': 'contract_expiry',
                'end_reason': 'انتهاء مدة العقد',
            },
            requested_by=self.requester,
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)

        action.status = PendingAction.Status.APPROVED
        action.save(update_fields=['status'])
        execute_pending_action(action, self.approver)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.TERMINATED)


class EndOfServiceContractExpiryTests(_BaseExecutorTests):
    def setUp(self):
        super().setUp()
        self.employee.hire_date = date(2019, 1, 1)
        self.employee.save(update_fields=['hire_date'])

    def test_contract_expiry_uses_full_eosb_without_resignation_factor(self):
        action = self._make_action('end_of_service', {
            'end_date': '2026-05-01',
            'terminated_by': 'contract_expiry',
            'end_reason': 'انتهاء مدة العقد',
        })
        msg = execute_pending_action(action, self.approver)
        self.assertIn('مكافأة', msg)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.TERMINATED)
        self.assertIn('انتهاء العقد بانتهاء مدته', self.employee.end_reason)
        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        )
        self.assertIn('انتهاء عقد بانتهاء مدته', st.title)
        self.assertIn('راتب كامل', st.content)


class EndOfServiceArticle77Tests(_BaseExecutorTests):
    def setUp(self):
        super().setUp()
        self.employee.hire_date = date(2019, 1, 1)
        self.employee.save(update_fields=['hire_date'])

    def test_article_77_from_company_adds_full_eosb_and_penalty(self):
        action = self._make_action('end_of_service', {
            'end_date': '2026-05-01',
            'terminated_by': 'article_77',
            'article_77_party': 'company',
            'end_reason': 'سبب غير مشروع',
        })
        msg = execute_pending_action(action, self.approver)
        self.assertIn('جزاء', msg)
        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        )
        self.assertIn('المادة 77', st.title)
        self.assertIn('شرط جزائي', st.content)
        self.assertIn('جزاء', st.content)

    def test_article_77_from_employee_uses_resignation_factor(self):
        action = self._make_action('end_of_service', {
            'end_date': '2026-05-01',
            'terminated_by': 'article_77',
            'article_77_party': 'employee',
            'end_reason': 'سبب غير مشروع',
        })
        execute_pending_action(action, self.approver)
        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        )
        self.assertIn('معامل الاستقالة', st.content)


class EndOfServiceArticle74Tests(_BaseExecutorTests):
    def setUp(self):
        super().setUp()
        self.employee.hire_date = date(2019, 1, 1)
        self.employee.save(update_fields=['hire_date'])

    def test_article_74_from_company_uses_standard_eosb(self):
        action = self._make_action('end_of_service', {
            'end_date': '2026-05-01',
            'terminated_by': 'article_74',
            'article_party': 'company',
            'end_reason': 'اتفاق متبادل',
        })
        msg = execute_pending_action(action, self.approver)
        self.assertIn('مكافأة', msg)
        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        )
        self.assertIn('المادة 74', st.title)
        self.assertIn('راتب كامل', st.content)

    def test_article_74_from_employee_uses_third_and_two_thirds(self):
        action = self._make_action('end_of_service', {
            'end_date': '2026-05-01',
            'terminated_by': 'article_74',
            'article_party': 'employee',
            'end_reason': 'اتفاق متبادل',
        })
        execute_pending_action(action, self.approver)
        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        )
        self.assertIn('⅓ راتب', st.content)
        self.assertIn('⅔ راتب', st.content)


class EndOfServiceArticle80Tests(_BaseExecutorTests):
    def setUp(self):
        super().setUp()
        self.employee.hire_date = date(2019, 1, 1)
        self.employee.available_leave_balance = Decimal('5')
        self.employee.save(update_fields=['hire_date', 'available_leave_balance'])

    def test_article_80_pays_leave_only_without_eosb(self):
        action = self._make_action('end_of_service', {
            'end_date': '2026-05-01',
            'terminated_by': 'article_80',
            'end_reason': 'سبب مشروع',
        })
        msg = execute_pending_action(action, self.approver)
        self.assertIn('رصيد إجازات', msg)
        self.assertNotIn('مكافأة:', msg)
        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        )
        self.assertIn('المادة 80', st.title)
        self.assertIn('بدون مكافأة نهاية خدمة', st.content)
        self.assertIn('30 يوم/سنة', st.content)
        self.assertIn('إجازة', st.content)


class EndOfServiceProbationEndTests(_BaseExecutorTests):
    def setUp(self):
        super().setUp()
        self.employee.hire_date = date(2026, 1, 1)
        self.employee.available_leave_balance = Decimal('2')
        self.employee.save(update_fields=['hire_date', 'available_leave_balance'])

    def test_probation_end_pays_leave_only_without_eosb(self):
        action = self._make_action('end_of_service', {
            'end_date': '2026-04-01',
            'terminated_by': 'probation_end',
            'end_reason': 'انتهاء فترة التجربة',
        })
        msg = execute_pending_action(action, self.approver)
        self.assertIn('نهاية فترة التجربة', msg)
        self.assertIn('رصيد إجازات', msg)
        self.assertNotIn('مكافأة:', msg)
        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        )
        self.assertIn('نهاية فترة التجربة', st.title)
        self.assertIn('21 يوم/سنة', st.content)
        self.assertNotIn('30 يوم/سنة', st.content)


class ReactivateExecutorTests(_BaseExecutorTests):
    def setUp(self):
        super().setUp()
        self.employee.status = Employee.Status.TERMINATED
        self.employee.end_date = date(2024, 12, 31)
        self.employee.end_reason = 'انتهاء عقد'
        self.employee.available_leave_balance = Decimal('3')
        self.employee.save()

    def test_reactivate_resets_employee_state(self):
        action = self._make_action('reactivate', {
            'new_hire_date': '2025-01-15',
            'reactivation_reason': 'تجديد التعاقد',
            'new_status': Employee.Status.ACTIVE,
        })
        execute_pending_action(action, self.approver)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)
        self.assertEqual(self.employee.hire_date, date(2025, 1, 15))
        self.assertIsNone(self.employee.end_date)
        self.assertEqual(self.employee.end_reason, '')
        self.assertEqual(self.employee.available_leave_balance, Decimal('0'))


class SalaryAdjustExecutorTests(_BaseExecutorTests):
    def test_salary_adjust_updates_basic_and_logs_diff(self):
        old_basic = self.employee.basic_salary
        action = self._make_action('salary_adjust', {
            'new_basic_salary': '4500',
            'reason': 'ترقية',
            'effective_date': '2025-04-01',
        })
        execute_pending_action(action, self.approver)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.basic_salary, Decimal('4500'))

        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.SALARY_ADJUST,
        )
        self.assertIn(str(old_basic), st.content)
        self.assertIn('4500', st.content)
        self.assertIn('ترقية', st.content)


class TransferExecutorTests(_BaseExecutorTests):
    def test_transfer_changes_branch(self):
        action = self._make_action('transfer', {
            'new_branch_id': self.branch_b.id,
            'transfer_date': '2025-05-01',
            'reason': 'نقل إداري',
        })
        execute_pending_action(action, self.approver)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.branch_id, self.branch_b.id)

        st = EmployeeStatement.objects.get(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TRANSFER,
        )
        self.assertIn('فرع A', st.content)
        self.assertIn('فرع B', st.content)


class AtomicityTests(_BaseExecutorTests):
    def test_executor_failure_rolls_back_employee_changes(self):
        original_status = self.employee.status
        action = self._make_action('terminate', {
            'end_date': '2025-03-01',
            'end_reason': 'اختبار rollback',
        })

        with patch(
            'apps.employees.models.EmployeeStatement.objects.create',
            side_effect=RuntimeError('فشل اصطناعي'),
        ):
            with self.assertRaises(RuntimeError):
                execute_pending_action(action, self.approver)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, original_status)
        self.assertIsNone(self.employee.end_date)

        action.refresh_from_db()
        self.assertIn('فشل اصطناعي', action.execution_error)
        self.assertIsNone(action.executed_at)

    def test_unknown_action_type_raises(self):
        action = self._make_action('leave', {})
        action.action_type = 'unknown_type'
        action.save(update_fields=['action_type'])

        with self.assertRaises(ValueError):
            execute_pending_action(action, self.approver)


class AuditDiffTests(TestCase):
    def test_work_schedule_summary_not_raw_json(self):
        from apps.core.services.audit_diff import _summarize_work_schedule

        raw = '{"version": 3, "boxes": [{"id": "b1", "year": 2026, "month": 5}, {"year": 2026, "month": 6}]}'
        s = _summarize_work_schedule(raw)
        self.assertIn('2 شهر', s)
        self.assertIn('5/2026', s)
        self.assertNotIn('"boxes"', s)

    def test_file_field_shows_basename_only(self):
        from apps.core.services.audit_diff import _format_value

        old = 'employees/id/old.png'
        new = 'HR/employees/id/2026/new_abc.png'
        self.assertEqual(_format_value('id_document', old), 'old.png')
        self.assertEqual(_format_value('id_document', new), 'new_abc.png')

    def test_model_label_not_historical_prefix(self):
        from apps.core.services.audit_diff import _model_label_ar
        from apps.employees.models import Employee

        Hist = Employee.history.model
        self.assertEqual(_model_label_ar(Hist()), 'موظف')

    def test_meaningless_change_filtered(self):
        from apps.core.services.audit_diff import _is_meaningless_change

        self.assertTrue(_is_meaningless_change('—', '—'))
        self.assertTrue(_is_meaningless_change('علي', 'علي'))
        self.assertFalse(_is_meaningless_change('علي', 'علي احمد'))


class AuditFeedTests(TestCase):
    def test_collect_returns_list(self):
        from apps.core.services.audit_feed import collect_audit_events

        rows = collect_audit_events(branch_ids=None, source='all', limit=20)
        self.assertIsInstance(rows, list)

    def test_password_change_appears_in_system_audit_feed(self):
        from apps.core.models import SystemAuditLog
        from apps.core.services.audit_feed import collect_audit_events
        from apps.core.services.system_audit import log_system_audit

        user = User.objects.create_user(username='pwd_audit', password='oldpass12')
        log_system_audit(
            request=None,
            action=SystemAuditLog.Action.PASSWORD_CHANGE_SELF,
            summary='تغيير كلمة المرور',
            details='اختبار تسجيل تغيير كلمة المرور',
            target_user=user,
        )
        rows = collect_audit_events(branch_ids=None, source='system', limit=10)
        self.assertTrue(any(r.operation_ar == 'تغيير كلمة المرور' for r in rows))
        self.assertTrue(any('اختبار' in r.details for r in rows))


class AuditHistoryViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة تدقيق')
        cls.branch = Branch.objects.create(name='فرع', code='AUD-1', company=cls.company)
        role = Role.objects.create(
            name='مدير موارد تدقيق',
            role_type=Role.RoleType.HR_MANAGER,
            is_system_role=False,
        )
        cls.gm = User.objects.create_user(username='aud_gm', password='x', is_active=True)
        from apps.core.models import UserProfile

        p = UserProfile.objects.get(user=cls.gm)
        p.role = role
        p.branch = cls.branch
        p.save(update_fields=['role', 'branch'])

    def test_superuser_can_open_audit_history(self):
        su = User.objects.create_user(username='aud_su', password='x', is_superuser=True, is_staff=True)
        c = Client()
        self.assertTrue(c.login(username='aud_su', password='x'))
        r = c.get(reverse('web:audit_history'))
        self.assertEqual(r.status_code, 200)

    def test_hr_manager_can_open_audit_history(self):
        c = Client()
        self.assertTrue(c.login(username='aud_gm', password='x'))
        r = c.get(reverse('web:audit_history'))
        self.assertEqual(r.status_code, 200)

    def test_regular_user_redirects_from_audit_history(self):
        User.objects.create_user(username='aud_u', password='x', is_active=True)
        c = Client()
        self.assertTrue(c.login(username='aud_u', password='x'))
        r = c.get(reverse('web:audit_history'))
        self.assertEqual(r.status_code, 302)


class FinalSettlementParseTests(TestCase):
    def test_parse_tolerates_star_and_spacing(self):
        from apps.core.web_views.hr_forms import _parse_final_settlement_statement

        text = (
            '★ إجمالي المستحقات: 3740.00 ر.س\n'
            '  (مكافأة 3500.00 + إجازة 240.00)\n'
            'رصيد الإجازة: 1.8 يوم × 133.33 = 240.00 ر.س\n'
        )
        d = _parse_final_settlement_statement(text)
        self.assertEqual(d.get('total_entitlement'), '3740.00')
        self.assertEqual(d.get('eosb_amount'), '3500.00')
        self.assertEqual(d.get('leave_comp'), '240.00')
        self.assertEqual(d.get('leave_days'), '1.8')


class HRFormPrintViewTests(TestCase):
    """طباعة النماذج الرسمية تمرّر form_type ثم employee_id — لا تعارض مع فحص الفرع."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة نماذج')
        cls.branch = Branch.objects.create(name='فرع', code='HF-1', company=cls.company)
        cls.employee = Employee.objects.create(
            name='موظف للنماذج',
            branch=cls.branch,
            status=Employee.Status.ACTIVE,
        )
        cls.su = User.objects.create_user(
            username='hrform_su', password='x', is_superuser=True, is_staff=True,
        )

    def test_warning_notice_print_returns_200(self):
        c = Client()
        self.assertTrue(c.login(username='hrform_su', password='x'))
        url = reverse(
            'web:hr_form_print',
            kwargs={'form_type': 'warning_notice', 'employee_id': self.employee.id},
        )
        r = c.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.employee.name)

    def test_hr_forms_employee_search_returns_matches(self):
        c = Client()
        self.assertTrue(c.login(username='hrform_su', password='x'))
        r = c.get(reverse('web:hr_forms_employee_search'), {'q': 'موظف'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(data['total'], 1)
        self.assertTrue(any(x['id'] == self.employee.id for x in data['results']))


class PasswordChangeViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='pw_ch_user',
            password='OldPwd29!xYz',
            is_active=True,
        )

    def test_anonymous_redirects_to_login(self):
        c = Client()
        r = c.get(reverse('web:auth:password_change'))
        self.assertEqual(r.status_code, 302)

    def test_get_form_when_logged_in(self):
        c = Client()
        self.assertTrue(c.login(username='pw_ch_user', password='OldPwd29!xYz'))
        r = c.get(reverse('web:auth:password_change'))
        self.assertEqual(r.status_code, 200)

    def test_post_changes_password(self):
        c = Client()
        self.assertTrue(c.login(username='pw_ch_user', password='OldPwd29!xYz'))
        new_pw = 'QazWsx#9mKp2vLx8'
        r = c.post(
            reverse('web:auth:password_change'),
            {
                'old_password': 'OldPwd29!xYz',
                'new_password1': new_pw,
                'new_password2': new_pw,
            },
        )
        self.assertEqual(r.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_pw))


# ──────────────────────────────────────────────────────────────────────
# Forms validation tests
# ──────────────────────────────────────────────────────────────────────
from apps.core.forms import RoleForm, BranchForm, UserCreateForm, UserEditForm, CostCenterForm, DepartmentForm


class RoleFormTests(TestCase):
    def test_valid(self):
        f = RoleForm(data={'name': 'دور جديد', 'role_type': 'employee', 'description': '', 'is_active': '1'})
        self.assertTrue(f.is_valid(), f.errors)

    def test_invalid_role_type(self):
        f = RoleForm(data={'name': 'x', 'role_type': 'bogus'})
        self.assertFalse(f.is_valid())


class BranchFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='ش')
        cls.user = User.objects.create_user(username='m', password='x', is_active=True)
        cls.existing = Branch.objects.create(name='قائم', code='EX', company=cls.company, manager=cls.user)

    def test_valid(self):
        f = BranchForm(data={'name': 'فرع', 'code': 'NEW', 'manager': self.user.pk, 'is_active': '1'})
        self.assertTrue(f.is_valid(), f.errors)

    def test_duplicate_code(self):
        f = BranchForm(data={'name': 'x', 'code': 'EX', 'manager': self.user.pk})
        self.assertFalse(f.is_valid())
        self.assertIn('code', f.errors)

    def test_manager_optional(self):
        f = BranchForm(data={'name': 'x', 'code': 'NEW', 'is_active': '1'})
        self.assertTrue(f.is_valid(), f.errors)
        branch = f.save(commit=False)
        branch.company = self.company
        branch.save()
        self.assertIsNone(branch.manager_id)


class UserFormsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.existing = User.objects.create_user(username='taken', password='x')

    def test_create_duplicate_username(self):
        f = UserCreateForm(data={'username': 'taken', 'password': 'pass1234'})
        self.assertFalse(f.is_valid())
        self.assertIn('username', f.errors)

    def test_create_password_required(self):
        f = UserCreateForm(data={'username': 'newone'})
        self.assertFalse(f.is_valid())
        self.assertIn('password', f.errors)

    def test_create_valid(self):
        f = UserCreateForm(data={'username': 'newone', 'password': 'pass1234', 'is_active': '1'})
        self.assertTrue(f.is_valid(), f.errors)

    def test_edit_allows_same_username(self):
        f = UserEditForm(data={'username': 'taken'}, instance=self.existing)
        self.assertTrue(f.is_valid(), f.errors)


class CostCenterFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='ش')
        cls.branch = Branch.objects.create(name='ف', code='BB', company=cls.company)
        from apps.cost_centers.models import CostCenter
        cls.existing = CostCenter.objects.create(code='CC1', name='قائم', branch=cls.branch)

    def test_duplicate_code(self):
        f = CostCenterForm(data={'code': 'CC1', 'name': 'x'}, branch=self.branch)
        self.assertFalse(f.is_valid())

    def test_valid(self):
        f = CostCenterForm(data={'code': 'CC2', 'name': 'جديد'}, branch=self.branch)
        self.assertTrue(f.is_valid(), f.errors)


class DepartmentFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='ش')
        cls.branch = Branch.objects.create(name='ف', code='BD', company=cls.company)
        from apps.departments.models import Department
        cls.existing = Department.objects.create(code='D1', name='قائم', branch=cls.branch)

    def test_duplicate_code(self):
        f = DepartmentForm(data={'code': 'D1', 'name': 'x'}, branch=self.branch)
        self.assertFalse(f.is_valid())

    def test_valid(self):
        f = DepartmentForm(data={'code': 'D2', 'name': 'جديد'}, branch=self.branch)
        self.assertTrue(f.is_valid(), f.errors)


class MediaResolveTests(TestCase):
    def test_iter_r2_key_candidates_legacy_and_hr_layout(self):
        from apps.core.media_resolve import iter_r2_key_candidates

        path = 'employees/statements/photo.jpg'
        keys = list(iter_r2_key_candidates(path))
        self.assertIn(path, keys)
        self.assertIn('HR/employees/statements/photo.jpg', keys)
        self.assertTrue(any(k.startswith('HR/employees/statements/') and k.endswith('/photo.jpg') for k in keys))

    def test_normalize_media_path_decodes_spaces(self):
        from apps.core.media_views import _normalize_media_path

        self.assertEqual(
            _normalize_media_path('employees/statements/a%20b.jpg'),
            'employees/statements/a b.jpg',
        )


class MediaAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة')
        cls.branch_a = Branch.objects.create(name='فرع أ', code='A', company=cls.company)
        cls.branch_b = Branch.objects.create(name='فرع ب', code='B', company=cls.company)
        cls.admin_user = User.objects.create_user(username='admin_media', password='x', is_superuser=True)
        cls.manager = User.objects.create_user(username='mgr_media', password='x', is_staff=True)
        role = Role.objects.create(
            name='مدير فرع وسائط',
            role_type=Role.RoleType.MANAGER,
        )
        from apps.core.models import Permission, UserProfile

        profile, _ = UserProfile.objects.get_or_create(user=cls.manager)
        profile.role = role
        profile.branch = cls.branch_a
        profile.save(update_fields=['role', 'branch'])
        cls.branch_a.manager = cls.manager
        cls.branch_a.save(update_fields=['manager'])
        cls.employee_a = Employee.objects.create(
            name='موظف أ',
            branch=cls.branch_a,
            status=Employee.Status.ACTIVE,
        )
        cls.employee_a.id_document = 'employees/id/emp_a_id.pdf'
        cls.employee_a.save(update_fields=['id_document'])
        cls._employees_view_perm = Permission.objects.get(code='employees.view')
        role.permissions.add(cls._employees_view_perm)

    def test_superuser_may_access_employee_file(self):
        from apps.core.services.media_access import user_may_access_media_path

        self.assertTrue(
            user_may_access_media_path(self.admin_user, 'employees/id/emp_a_id.pdf')
        )

    def _manager_user(self):
        """مستخدم مُحدَّث مع الملف والدور (يتجنب كاش profile القديم)."""
        if hasattr(self.manager, '_perm_codes_cache'):
            del self.manager._perm_codes_cache
        return User.objects.select_related('profile__role').get(pk=self.manager.pk)

    def test_branch_manager_denied_other_branch_file(self):
        from apps.core.services.media_access import user_may_access_media_path

        other = Employee.objects.create(
            name='موظف ب',
            branch=self.branch_b,
            status=Employee.Status.ACTIVE,
        )
        other.id_document = 'employees/id/emp_b_id.pdf'
        other.save(update_fields=['id_document'])

        self.assertFalse(
            user_may_access_media_path(
                self._manager_user(), 'employees/id/emp_b_id.pdf'
            )
        )

    def test_branch_manager_allowed_own_branch_file(self):
        from apps.core.services.media_access import user_may_access_media_path

        self.assertTrue(
            user_may_access_media_path(
                self._manager_user(), 'employees/id/emp_a_id.pdf'
            )
        )


class ParseMultiFilterIdsTests(TestCase):
    def test_post_reads_branch_id_not_get(self):
        from django.test import RequestFactory

        from apps.core.filter_utils import parse_multi_filter_ids

        factory = RequestFactory()
        request = factory.post(
            '/payroll/',
            data={'branch_id': ['1', '9', '12']},
        )
        request.GET = request.GET.copy()
        request.GET.setlist('branch', ['99'])
        ids = parse_multi_filter_ids(request, 'branch_id')
        self.assertEqual(ids, [1, 9, 12])

    def test_post_dedupes_duplicate_branch_id(self):
        from django.test import RequestFactory

        from apps.core.filter_utils import parse_multi_filter_ids

        factory = RequestFactory()
        request = factory.post(
            '/payroll/',
            data={'branch_id': ['6', '6']},
        )
        ids = parse_multi_filter_ids(request, 'branch_id')
        self.assertEqual(ids, [6])


class DecimalNumberInputTests(TestCase):
    def test_format_decimal_uses_dot(self):
        from decimal import Decimal

        from apps.core.widgets import DecimalNumberInput, format_decimal_for_number_input

        self.assertEqual(format_decimal_for_number_input(Decimal('10000.00')), '10000.00')
        self.assertEqual(format_decimal_for_number_input('10000,50'), '10000.50')
        self.assertEqual(format_decimal_for_number_input(None), '')
        widget = DecimalNumberInput()
        self.assertEqual(widget.format_value(Decimal('5000.25')), '5000.25')

    def test_hr_form_renders_decimal_with_dot(self):
        from apps.core.forms import SalaryAdjustForm

        form = SalaryAdjustForm(initial={'new_basic_salary': '7500.00'})
        html = str(form['new_basic_salary'])
        self.assertIn('value="7500.00"', html)
        self.assertNotIn('value="7500,00"', html)
