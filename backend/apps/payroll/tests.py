"""
Tests for payroll engine — build, lock, unlock, deduction rules.
"""
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Company, Branch
from apps.setup.models import Sponsorship
from apps.employees.models import (
    Employee,
    EmployeeAbsence,
    EmployeeLeave,
    EmployeeStatement,
    EmployeeLoan,
    LoanInstallment,
)
from apps.payroll.models import PayrollAllocationLine, PayrollRun
from apps.payroll.services.engine import (
    build_payroll_run,
    build_consolidated_payroll_run,
    lock_payroll_run,
    unlock_payroll_run,
)
from apps.payroll.services.payroll_line_columns import resolve_cell_value
from apps.payroll.services.period_eligibility import employee_payroll_period
from apps.payroll.services.transfer_payroll import (
    build_payroll_detailed_run,
    transfers_in_period,
)

User = get_user_model()


class PayrollEngineTests(TestCase):
    """Integration tests against build_payroll_run / lock / unlock."""

    def setUp(self):
        self.company = Company.objects.create(name='Test Co')
        self.branch = Branch.objects.create(
            name='Branch A', code='TST01', company=self.company,
        )
        self.user = User.objects.create_user(username='payroll_tester', password='test-pass-123')
        self.sponsorship = Sponsorship.objects.create(code='SP01', company_name='كفالة تجريبية')
        salary_defaults = dict(
            branch=self.branch,
            status=Employee.Status.ACTIVE,
            hire_date=date(2020, 1, 1),
            basic_salary=Decimal('3000'),
            housing_allowance=Decimal('1000'),
            transport_allowance=Decimal('500'),
            other_allowance=Decimal('0'),
            cash_amount=Decimal('0'),
            insurance_deduction_rate=Decimal('10'),
        )
        self.employee_cash = Employee.objects.create(
            name='موظف نقدي', sponsorship=None, **salary_defaults,
        )
        self.employee_transfer = Employee.objects.create(
            name='موظف تحويل', sponsorship=self.sponsorship, **salary_defaults,
        )
        self.employee = self.employee_transfer

    def test_build_computes_gross_and_insurance(self):
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run.lines.get(employee=self.employee)
        self.assertEqual(line.gross_salary, Decimal('4500.00'))
        self.assertEqual(line.insurance_deduction, Decimal('450.00'))
        self.assertGreater(line.net_salary, Decimal('0'))

    def test_build_uses_standard_30_day_month(self):
        run = build_payroll_run(
            self.branch, 2026, 2, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run.lines.get(employee=self.employee)
        self.assertEqual(line.month_days, 30)
        expected_daily = (Decimal('4500') / Decimal('30')).quantize(Decimal('0.01'))
        self.assertEqual(line.daily_rate, expected_daily)

    def test_build_includes_absence_deduction(self):
        """خصم الغياب يُحسب دائماً من الإجمالي ÷ 30 وليس من المبلغ المخزّن قديماً."""
        EmployeeAbsence.objects.create(
            employee=self.employee,
            absence_date=date(2026, 3, 10),
            days=1,
            month_days=31,
            deduction_amount=Decimal('100.00'),
        )
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run.lines.get(employee=self.employee)
        expected = (Decimal('4500') / Decimal('30')).quantize(Decimal('0.01'))
        self.assertEqual(line.absence_deduction, expected)

    def test_build_unpaid_leave_deduction(self):
        EmployeeLeave.objects.create(
            employee=self.employee,
            leave_type=EmployeeLeave.LeaveType.UNPAID,
            date_from=date(2026, 3, 5),
            date_to=date(2026, 3, 6),
            days=Decimal('2'),
        )
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run.lines.get(employee=self.employee)
        daily = (Decimal('4500') / Decimal('30')).quantize(Decimal('0.01'))
        expected = (daily * Decimal('2')).quantize(Decimal('0.01'))
        self.assertEqual(line.unpaid_leave_deduction, expected)

    def test_build_penalty_deduction(self):
        EmployeeStatement.objects.create(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.PENALTY,
            title='غرامة',
            statement_date=date(2026, 3, 15),
            deduction_amount=Decimal('50.00'),
        )
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run.lines.get(employee=self.employee)
        self.assertEqual(line.penalty_deduction, Decimal('50.00'))

    def test_net_salary_never_negative(self):
        self.employee.insurance_deduction_rate = Decimal('100')
        self.employee.save(update_fields=['insurance_deduction_rate'])
        EmployeeStatement.objects.create(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.PENALTY,
            title='غرامة كبيرة',
            statement_date=date(2026, 3, 15),
            deduction_amount=Decimal('5000.00'),
        )
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run.lines.get(employee=self.employee)
        self.assertGreaterEqual(line.net_salary, Decimal('0'))
        self.assertEqual(line.net_salary, Decimal('0'))

    def test_build_loan_installment(self):
        loan = EmployeeLoan.objects.create(
            employee=self.employee,
            amount=Decimal('300'),
            monthly_deduction=Decimal('100'),
            installments=3,
            issued_at=date(2026, 2, 1),
            first_deduction_date=date(2026, 3, 1),
        )
        loan.generate_installments()
        self.assertTrue(
            loan.installments_log.filter(period_year=2026, period_month=3).exists()
        )
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run.lines.get(employee=self.employee)
        self.assertEqual(line.loan_deduction, Decimal('100.00'))

    def test_rebuild_locked_raises(self):
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        lock_payroll_run(run, self.user)
        with self.assertRaises(ValueError) as ctx:
            build_payroll_run(
                self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
            )
        self.assertIn('مُغلق', str(ctx.exception))

    def test_cash_mode_excludes_sponsored_employees(self):
        run = build_payroll_run(
            self.branch, 2026, 4, self.user, salary_mode=PayrollRun.SalaryMode.CASH,
        )
        self.assertEqual(run.lines.count(), 1)
        self.assertEqual(run.lines.get().employee_id, self.employee_cash.id)

    def test_transfer_mode_excludes_unsponsored_employees(self):
        run = build_payroll_run(
            self.branch, 2026, 5, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        self.assertEqual(run.lines.count(), 1)
        self.assertEqual(run.lines.get().employee_id, self.employee_transfer.id)

    def test_same_branch_month_allows_two_runs_by_salary_mode(self):
        run_cash = build_payroll_run(
            self.branch, 2026, 6, self.user, salary_mode=PayrollRun.SalaryMode.CASH,
        )
        run_transfer = build_payroll_run(
            self.branch, 2026, 6, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        self.assertNotEqual(run_cash.id, run_transfer.id)
        self.assertEqual(run_cash.employees_count, 1)
        self.assertEqual(run_transfer.employees_count, 1)

    def test_consolidated_run_single_draft_for_multiple_branches(self):
        branch_b = Branch.objects.create(name='Branch B', code='TST02', company=self.company)
        Employee.objects.create(
            name='موظف فرع ب', branch=branch_b, sponsorship=self.sponsorship,
            status=Employee.Status.ACTIVE, hire_date=date(2020, 1, 1),
            basic_salary=Decimal('2000'), housing_allowance=Decimal('0'),
            transport_allowance=Decimal('0'), other_allowance=Decimal('0'),
            cash_amount=Decimal('0'), insurance_deduction_rate=Decimal('0'),
        )
        build_payroll_run(
            self.branch, 2026, 7, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        build_payroll_run(
            branch_b, 2026, 7, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        self.assertEqual(
            PayrollRun.objects.filter(
                period_year=2026, period_month=7,
                run_kind=PayrollRun.RunKind.STANDARD,
                salary_mode=PayrollRun.SalaryMode.TRANSFER,
            ).count(),
            2,
        )
        run = build_consolidated_payroll_run(
            [self.branch, branch_b], 2026, 7, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        self.assertEqual(run.run_kind, PayrollRun.RunKind.CONSOLIDATED)
        self.assertIsNone(run.branch_id)
        self.assertEqual(run.employees_count, 2)
        self.assertEqual(
            PayrollRun.objects.filter(
                period_year=2026, period_month=7,
                run_kind=PayrollRun.RunKind.STANDARD,
                status=PayrollRun.Status.DRAFT,
            ).count(),
            0,
        )

    def test_consolidated_cash_run_single_draft_for_multiple_branches(self):
        branch_b = Branch.objects.create(name='Branch B Cash', code='TSC02', company=self.company)
        cash_defaults = dict(
            sponsorship=None,
            status=Employee.Status.ACTIVE,
            hire_date=date(2020, 1, 1),
            basic_salary=Decimal('2500'),
            housing_allowance=Decimal('0'),
            transport_allowance=Decimal('0'),
            other_allowance=Decimal('0'),
            cash_amount=Decimal('0'),
            insurance_deduction_rate=Decimal('0'),
        )
        Employee.objects.create(name='نقدي ب', branch=branch_b, **cash_defaults)
        build_payroll_run(
            self.branch, 2026, 8, self.user,
            salary_mode=PayrollRun.SalaryMode.CASH,
        )
        build_payroll_run(
            branch_b, 2026, 8, self.user,
            salary_mode=PayrollRun.SalaryMode.CASH,
        )
        run = build_consolidated_payroll_run(
            [self.branch, branch_b], 2026, 8, self.user,
            salary_mode=PayrollRun.SalaryMode.CASH,
        )
        self.assertEqual(run.run_kind, PayrollRun.RunKind.CONSOLIDATED)
        self.assertEqual(run.salary_mode, PayrollRun.SalaryMode.CASH)
        self.assertIsNone(run.sponsorship_id)
        self.assertEqual(run.employees_count, 2)
        self.assertEqual(
            PayrollRun.objects.filter(
                period_year=2026,
                period_month=8,
                salary_mode=PayrollRun.SalaryMode.CASH,
                run_kind=PayrollRun.RunKind.STANDARD,
                status=PayrollRun.Status.DRAFT,
            ).count(),
            0,
        )

    def test_lock_twice_raises(self):
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        lock_payroll_run(run, self.user)
        with self.assertRaises(ValueError):
            lock_payroll_run(run, self.user)

    def test_lock_links_absence_to_run(self):
        abs_rec = EmployeeAbsence.objects.create(
            employee=self.employee,
            absence_date=date(2026, 3, 12),
            days=1,
            month_days=31,
            deduction_amount=Decimal('75.00'),
        )
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        lock_payroll_run(run, self.user)
        abs_rec.refresh_from_db()
        self.assertEqual(abs_rec.applied_to_payroll_id, run.id)

    def test_mid_month_transfer_full_salary_on_new_branch_only(self):
        import json

        branch_b = Branch.objects.create(
            name='Branch B', code='TST02', company=self.company,
        )
        self.employee.branch = branch_b
        self.employee.save(update_fields=['branch'])
        EmployeeStatement.objects.create(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TRANSFER,
            title='نقل',
            statement_date=date(2026, 3, 15),
            content=json.dumps({
                'branch_changed': True,
                'branch_from': 'Branch A',
                'branch_to': 'Branch B',
                'branch_from_id': self.branch.id,
                'branch_to_id': branch_b.id,
            }, ensure_ascii=False),
        )
        run_old = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        self.assertEqual(run_old.lines.count(), 0)

        run_new = build_payroll_run(
            branch_b, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run_new.lines.get()
        self.assertEqual(line.net_salary, Decimal('4050.00'))
        self.assertIn('transfer', line.breakdown)
        self.assertEqual(line.breakdown['transfer']['rule'], 'full_salary_new_branch')

        detailed = build_payroll_detailed_run(
            self.company, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        rows = list(detailed.allocation_lines.order_by('branch__name'))
        self.assertEqual(len(rows), 2)
        old_row = next(r for r in rows if r.branch_id == self.branch.id)
        new_row = next(r for r in rows if r.branch_id == branch_b.id)
        self.assertEqual(old_row.net_amount, Decimal('0'))
        self.assertFalse(old_row.bears_salary)
        self.assertEqual(new_row.net_amount, line.net_salary)
        self.assertTrue(new_row.bears_salary)

    def test_mid_month_hire_prorates_gross_and_export_period(self):
        """مباشرة منتصف الشهر: فترة فعلية + راتب نسبي وليس شهراً كاملاً."""
        haroon = Employee.objects.create(
            name='هارون',
            branch=self.branch,
            sponsorship=self.sponsorship,
            status=Employee.Status.ACTIVE,
            hire_date=date(2026, 7, 20),
            basic_salary=Decimal('3000'),
            housing_allowance=Decimal('1000'),
            transport_allowance=Decimal('500'),
            other_allowance=Decimal('0'),
            cash_amount=Decimal('0'),
            insurance_deduction_rate=Decimal('10'),
        )
        period = employee_payroll_period(
            period_year=2026,
            period_month=7,
            hire_date=haroon.hire_date,
        )
        self.assertEqual(period['period_start'], date(2026, 7, 20))
        self.assertEqual(period['period_end'], date(2026, 7, 31))
        self.assertEqual(period['payable_base_days'], Decimal('12'))

        run = build_payroll_run(
            self.branch, 2026, 7, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        line = run.lines.get(employee=haroon)
        expected_gross = (Decimal('4500') * Decimal('12') / Decimal('30')).quantize(Decimal('0.01'))
        self.assertEqual(line.gross_salary, expected_gross)
        self.assertEqual(line.insurance_deduction, (expected_gross * Decimal('0.10')).quantize(Decimal('0.01')))
        self.assertEqual(resolve_cell_value(line, run, 'period_start'), '2026-07-20')
        self.assertEqual(resolve_cell_value(line, run, 'period_end'), '2026-07-31')
        self.assertEqual(resolve_cell_value(line, run, 'worked_days'), Decimal('12'))

    def test_future_hire_excluded_from_payroll_run(self):
        Employee.objects.create(
            name='موظف مستقبلي',
            branch=self.branch,
            sponsorship=self.sponsorship,
            status=Employee.Status.ACTIVE,
            hire_date=date(2026, 8, 1),
            basic_salary=Decimal('3000'),
            housing_allowance=Decimal('0'),
            transport_allowance=Decimal('0'),
            other_allowance=Decimal('0'),
            cash_amount=Decimal('0'),
            insurance_deduction_rate=Decimal('0'),
        )
        run = build_payroll_run(
            self.branch, 2026, 7, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        self.assertEqual(run.lines.count(), 1)
        self.assertEqual(run.lines.get().employee_id, self.employee_transfer.id)

    def test_transfers_in_period_parses_statement(self):
        import json

        EmployeeStatement.objects.create(
            employee=self.employee,
            statement_type=EmployeeStatement.StatementType.TRANSFER,
            title='نقل',
            statement_date=date(2026, 4, 10),
            content=json.dumps({
                'branch_changed': True,
                'branch_from': 'Branch A',
                'branch_to': 'Branch A',
                'branch_from_id': self.branch.id,
                'branch_to_id': self.branch.id,
            }, ensure_ascii=False),
        )
        evts = transfers_in_period(self.company.id, 2026, 4)
        self.assertNotIn(self.employee.id, evts)

    def test_relock_after_unlock_no_duplicate_ledger(self):
        from apps.employees.models import EmployeeLedger

        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        lock_payroll_run(run, self.user)
        self.assertEqual(
            EmployeeLedger.objects.filter(
                payroll_run=run,
                employee=self.employee,
            ).count(),
            1,
        )
        unlock_payroll_run(run, self.user)
        self.assertEqual(EmployeeLedger.objects.filter(payroll_run=run).count(), 0)
        lock_payroll_run(run, self.user)
        self.assertEqual(
            EmployeeLedger.objects.filter(
                payroll_run=run,
                employee=self.employee,
            ).count(),
            1,
        )

    def test_unlock_clears_payroll_links_and_returns_draft(self):
        abs_rec = EmployeeAbsence.objects.create(
            employee=self.employee,
            absence_date=date(2026, 3, 12),
            days=1,
            month_days=31,
            deduction_amount=Decimal('75.00'),
        )
        run = build_payroll_run(
            self.branch, 2026, 3, self.user,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            sponsorship_id=self.sponsorship.id,
        )
        lock_payroll_run(run, self.user)
        unlock_payroll_run(run, self.user)
        abs_rec.refresh_from_db()
        run.refresh_from_db()
        self.assertIsNone(abs_rec.applied_to_payroll_id)
        self.assertEqual(run.status, PayrollRun.Status.DRAFT)
