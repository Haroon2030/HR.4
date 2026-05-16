from django.test import TestCase
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from apps.employees.models import Employee, EmployeeLoan, LoanInstallment
from apps.setup.models import Sponsorship

class EmployeeModelTests(TestCase):
    def setUp(self):
        # Create a mock sponsorship to test accrued leave days calculation
        self.sponsorship = Sponsorship.objects.create(
            code="SP-TEST",
            company_name="Test Sponsorship",
        )
        
        # Create an employee
        self.employee = Employee.objects.create(
            name="Test Employee",
            basic_salary=Decimal('5000.00'),
            housing_allowance=Decimal('1000.00'),
            transport_allowance=Decimal('500.00'),
            other_allowance=Decimal('0.00'),
            cash_amount=Decimal('0.00'),
            hire_date=date(2023, 1, 1),
            sponsorship=self.sponsorship,
            available_leave_balance=Decimal('5.0')  # 5 days used
        )

    def test_total_salary(self):
        """Test total salary property calculation"""
        expected_total = Decimal('6500.00')
        self.assertEqual(self.employee.total_salary, expected_total)

    def test_daily_wage(self):
        """Test daily wage calculation (total_salary / 30)"""
        expected_daily_wage = (Decimal('6500.00') / Decimal('30')).quantize(Decimal('0.01'))
        self.assertEqual(self.employee.daily_wage, expected_daily_wage)

    def test_accrued_leave_days(self):
        """Test accrued leave days calculation (21 days per year)"""
        # Let's set end_date to a fixed date to have deterministic tests
        self.employee.end_date = date(2024, 1, 1) # Exactly 1 year
        expected_accrued = Decimal('21.0') # 365 days -> 21.0
        self.assertEqual(self.employee.accrued_leave_days, expected_accrued)

    def test_remaining_leave_days(self):
        """Test remaining leave days calculation (accrued - used)"""
        self.employee.end_date = date(2024, 1, 1)
        # Accrued = 21, Used = 5
        expected_remaining = Decimal('16.0')
        self.assertEqual(self.employee.remaining_leave_days, expected_remaining)

    def test_leave_compensation(self):
        """Test leave compensation (remaining_leave_days * daily_wage)"""
        self.employee.end_date = date(2024, 1, 1)
        expected_compensation = (Decimal('16.0') * self.employee.daily_wage).quantize(Decimal('0.01'))
        self.assertEqual(self.employee.leave_compensation, expected_compensation)


class AccrualLedgerNotesTests(TestCase):
    def test_monthly_leave_and_eosb_formulas(self):
        from apps.employees.services.accrual_ledger_notes import (
            MONTHLY_LEAVE_ACCRUAL_DAYS,
            compute_monthly_ledger_amounts,
        )

        gross = Decimal('4000')
        daily = (gross / Decimal('30')).quantize(Decimal('0.01'))
        calc = compute_monthly_ledger_amounts(
            gross_salary=gross,
            daily_rate=daily,
            hire_date=date(2026, 1, 1),
            period_year=2026,
            period_month=6,
        )
        self.assertEqual(MONTHLY_LEAVE_ACCRUAL_DAYS, Decimal('1.75'))
        self.assertEqual(calc['leave_days'], Decimal('1.75'))
        self.assertEqual(calc['leave_amount'], Decimal('233.33'))
        self.assertEqual(calc['eosb'], Decimal('166.67'))  # 4000/24

    def test_monthly_notes_contains_formulas(self):
        from apps.employees.services.accrual_ledger_notes import build_monthly_payroll_notes

        notes = build_monthly_payroll_notes(
            period_year=2026,
            period_month=6,
            month_days=30,
            gross_salary=Decimal('4000'),
            daily_rate=Decimal('133.33'),
            hire_date=date(2026, 1, 1),
            prev_leave_days=Decimal('1.72'),
            prev_leave_amount=Decimal('229.33'),
            prev_eosb=Decimal('164.20'),
            leave_days_change=Decimal('1.75'),
            leave_amount_change=Decimal('233.33'),
            eosb_amount_change=Decimal('166.67'),
            cumulative_leave_days=Decimal('3.47'),
            cumulative_leave_amount=Decimal('462.66'),
            cumulative_eosb=Decimal('330.87'),
            payroll_run_id=99,
        )
        self.assertIn('21 ÷ 12', notes)
        self.assertIn('4000 ÷ 24', notes)
        self.assertIn('مسير #99', notes)


class EmployeeLoanTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            name="Test Loan Employee",
            basic_salary=Decimal('5000.00'),
        )
        self.loan = EmployeeLoan.objects.create(
            employee=self.employee,
            amount=Decimal('1000.00'),
            monthly_deduction=Decimal('250.00'),
            installments=4,
            issued_at=date(2023, 1, 15),
            first_deduction_date=date(2023, 2, 1)
        )

    def test_remaining_balance_initial(self):
        """Test remaining balance before any installments are paid"""
        self.assertEqual(self.loan.remaining_balance, Decimal('1000.00'))

    def test_generate_installments(self):
        """Test the generation of loan installments"""
        self.loan.generate_installments()
        installments = self.loan.installments_log.all()
        self.assertEqual(installments.count(), 4)
        
        # Check first installment
        first_installment = installments.order_by('due_date').first()
        self.assertEqual(first_installment.amount, Decimal('250.00'))
        self.assertEqual(first_installment.due_date, date(2023, 2, 1))
        self.assertEqual(first_installment.status, LoanInstallment.Status.PENDING)

    def test_remaining_balance_after_payment(self):
        """Test remaining balance after an installment is paid"""
        self.loan.generate_installments()
        first_installment = self.loan.installments_log.order_by('due_date').first()
        first_installment.status = LoanInstallment.Status.PAID
        first_installment.save()
        
        self.assertEqual(self.loan.remaining_balance, Decimal('750.00'))
