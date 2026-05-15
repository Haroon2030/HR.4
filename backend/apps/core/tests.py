"""اختبارات لـ apps.core.services.pending_actions executors."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import Branch, Company, PendingAction, Role
from apps.core.services.pending_actions import execute_pending_action
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


class ContractEndExecutorTests(_BaseExecutorTests):
    def setUp(self):
        super().setUp()
        self.employee.hire_date = date(2019, 1, 1)
        self.employee.save(update_fields=['hire_date'])

    def test_contract_end_company_terminates(self):
        action = self._make_action('contract_end', {
            'end_date': '2026-05-01',
            'terminated_by': 'company',
            'end_reason': 'انتهاء عقد محدد المدة',
        })
        msg = execute_pending_action(action, self.approver)
        self.assertIn('مكافأة', msg)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.TERMINATED)
        self.assertEqual(self.employee.end_date, date(2026, 5, 1))
        st = EmployeeStatement.objects.filter(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TERMINATE,
        ).first()
        self.assertIsNotNone(st)
        self.assertIn('انتهاء عقد', st.title)


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


class AuditFeedTests(TestCase):
    def test_collect_returns_list(self):
        from apps.core.services.audit_feed import collect_audit_events

        rows = collect_audit_events(branch_ids=None, source='all', limit=20)
        self.assertIsInstance(rows, list)


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

    def test_manager_required(self):
        f = BranchForm(data={'name': 'x', 'code': 'NEW'})
        self.assertFalse(f.is_valid())
        self.assertIn('manager', f.errors)


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
