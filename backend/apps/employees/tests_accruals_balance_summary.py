from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.employees.models import Employee, EmployeeLedger
from apps.employees.services.employee_view_data import _accruals_balance_summary


class AccrualsBalanceSummaryTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            name='سيما',
            status=Employee.Status.TERMINATED,
            hire_date=date(2025, 1, 1),
            end_date=date(2026, 6, 30),
        )

    def test_settled_employee_shows_pre_settlement_balances(self):
        settlement = EmployeeLedger.objects.create(
            employee=self.employee,
            transaction_type=EmployeeLedger.TransactionType.FINAL_SETTLEMENT,
            date=date(2026, 6, 30),
            leave_days_change=Decimal('-31.50'),
            leave_amount_change=Decimal('-4620.10'),
            eosb_amount_change=Decimal('-3263.26'),
            cumulative_leave_days=Decimal('0'),
            cumulative_leave_amount=Decimal('0'),
            cumulative_eosb_amount=Decimal('0'),
        )
        summary = _accruals_balance_summary(self.employee, [settlement])
        self.assertTrue(summary['is_settled_snapshot'])
        self.assertEqual(summary['leave_days'], Decimal('31.50'))
        self.assertEqual(summary['leave_amount'], Decimal('4620.10'))
        self.assertEqual(summary['eosb_amount'], Decimal('3263.26'))

    def test_active_employee_uses_latest_cumulative(self):
        self.employee.status = Employee.Status.ACTIVE
        self.employee.save(update_fields=['status'])
        entry = EmployeeLedger.objects.create(
            employee=self.employee,
            transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
            date=date(2026, 6, 19),
            cumulative_leave_days=Decimal('10.00'),
            cumulative_leave_amount=Decimal('1500.00'),
            cumulative_eosb_amount=Decimal('900.00'),
        )
        summary = _accruals_balance_summary(self.employee, [entry])
        self.assertFalse(summary['is_settled_snapshot'])
        self.assertEqual(summary['leave_days'], Decimal('10.00'))
