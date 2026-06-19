from django.http import QueryDict
from django.test import TestCase
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from apps.employees.forms import EmployeeForm, EmploymentRequestEditForm
from apps.employees.models import Employee, EmployeeAbsence, EmployeeLoan, LoanInstallment, EmploymentRequest
from apps.setup.models import Nationality, Sponsorship

class SalaryPaymentSplitTests(TestCase):
    def test_transfer_employee_gets_full_bank_amount(self):
        from decimal import Decimal
        from apps.employees.models import Employee
        from apps.setup.models import Sponsorship
        from apps.employees.services.salary_payment import (
            contract_bank_transfer_amount,
            split_net_by_payment_mode,
        )

        sp = Sponsorship.objects.create(code='SP-1', company_name='كفالة')
        emp = Employee.objects.create(
            name='تحويل', sponsorship=sp, basic_salary=Decimal('8000'),
            housing_allowance=Decimal('2000'),
        )
        self.assertEqual(contract_bank_transfer_amount(emp), Decimal('10000.00'))
        net_cash, net_bank = split_net_by_payment_mode(Decimal('9500'), emp)
        self.assertEqual(net_cash, Decimal('0'))
        self.assertEqual(net_bank, Decimal('9500.00'))

    def test_cash_employee_gets_full_cash_net(self):
        from decimal import Decimal
        from apps.employees.models import Employee
        from apps.employees.services.salary_payment import split_net_by_payment_mode

        emp = Employee.objects.create(name='نقدي', basic_salary=Decimal('5000'))
        net_cash, net_bank = split_net_by_payment_mode(Decimal('5000'), emp)
        self.assertEqual(net_cash, Decimal('5000.00'))
        self.assertEqual(net_bank, Decimal('0'))

    def test_account_type_export_label_only_for_sponsored(self):
        from apps.employees.models import Employee, SalaryAccountType
        from apps.employees.services.salary_payment import account_type_export_label

        sp = Sponsorship.objects.create(code='SP-2', company_name='كفالة 2')
        sponsored = Employee.objects.create(
            name='بنكي',
            sponsorship=sp,
            account_type=SalaryAccountType.SARIE,
        )
        cash = Employee.objects.create(name='نقد')
        self.assertEqual(account_type_export_label(sponsored), 'SARIE')
        self.assertEqual(account_type_export_label(cash), '')


class EmployeeFormTests(TestCase):
    def test_empty_basic_salary_in_post_defaults_to_zero(self):
        employee = Employee.objects.create(name='هارون', hire_date=date(2026, 5, 14))
        form = EmployeeForm(
            data={
                'name': 'هارون',
                'contract_type': 'unlimited',
                'basic_salary': '',
                'housing_allowance': '',
                'transport_allowance': '',
                'other_allowance': '',
                'cash_amount': '',
                'insurance_deduction_rate': '',
                'available_leave_balance': '',
            },
            instance=employee,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.basic_salary, Decimal('0'))

    def test_saudi_employee_accepts_gosi_insurance_rate(self):
        saudi = Nationality.objects.create(name='سعودي', code='SA')
        form = EmployeeForm(
            data={
                'name': 'موظف سعودي',
                'nationality': str(saudi.pk),
                'contract_type': 'fixed',
                'insurance_deduction_rate': '10.75',
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.insurance_deduction_rate, Decimal('10.75'))

    def test_duplicate_post_insurance_rate_last_value_wins(self):
        """محاكاة إرسال حقلين بنفس الاسم — آخر قيمة هي التي يقرأها النموذج."""
        saudi = Nationality.objects.create(name='سعودي', code='SA')
        post = QueryDict(mutable=True)
        post.setlist('insurance_deduction_rate', ['10.75', '0'])
        post['name'] = 'موظف سعودي'
        post['nationality'] = str(saudi.pk)
        post['contract_type'] = 'fixed'
        form = EmployeeForm(data=post)
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_deduction_rate', form.errors)

    def test_employment_request_saudi_gosi_rate_saves(self):
        saudi = Nationality.objects.create(name='سعودي', code='SA')
        sp = Sponsorship.objects.create(code='SP-ER', company_name='كفالة')
        req = EmploymentRequest.objects.create(name='أحمد', nationality=saudi, sponsorship=sp)
        form = EmploymentRequestEditForm(
            data={
                'name': 'أحمد',
                'nationality': str(saudi.pk),
                'sponsorship': str(sp.pk),
                'insurance_deduction_rate': '10.25',
                'basic_salary': '3200',
                'housing_allowance': '800',
                'transport_allowance': '400',
                'cash_amount': '0',
            },
            instance=req,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.insurance_deduction_rate, Decimal('10.25'))


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

    def test_meal_allowance_in_total_but_excluded_from_eos_base(self):
        self.employee.meal_allowance = Decimal('500.00')
        self.assertEqual(self.employee.total_salary, Decimal('7000.00'))
        self.assertEqual(self.employee.salary_for_end_of_service, Decimal('6500.00'))

    def test_eosb_not_calculated_without_sponsorship(self):
        self.employee.sponsorship = None
        self.employee.basic_salary = Decimal('5000.00')
        self.assertFalse(self.employee.eligible_for_end_of_service)
        self.assertEqual(self.employee.salary_for_end_of_service, Decimal('0'))

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

    def test_absence_save_enforces_30_day_rule(self):
        """حفظ الغياب يعيد الحساب دائماً على ÷ 30 حتى لو أُدخلت قيم قديمة."""
        absence = EmployeeAbsence(
            employee=self.employee,
            absence_date=date(2026, 3, 10),
            days=2,
            month_days=31,
            deduction_amount=Decimal('999.00'),
        )
        absence.save()
        expected_daily = (Decimal('6500') / Decimal('30')).quantize(Decimal('0.01'))
        self.assertEqual(absence.month_days, 30)
        self.assertEqual(absence.daily_rate, expected_daily)
        self.assertEqual(absence.deduction_amount, (expected_daily * 2).quantize(Decimal('0.01')))


class LedgerBalanceTests(TestCase):
    def test_settlement_uses_ledger_cumulative_amount(self):
        from apps.employees.models import EmployeeLedger
        from apps.employees.services.ledger_balances import settlement_leave_from_ledger
        from apps.setup.models import Sponsorship

        sponsorship = Sponsorship.objects.create(code='SP-L', company_name='K')
        emp = Employee.objects.create(
            name='Ledger Emp',
            hire_date=date(2024, 1, 1),
            sponsorship=sponsorship,
            basic_salary=Decimal('3000'),
        )
        EmployeeLedger.objects.create(
            employee=emp,
            transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
            date=date(2025, 1, 1),
            leave_days_change=Decimal('10'),
            leave_amount_change=Decimal('1000'),
            cumulative_leave_days=Decimal('10'),
            cumulative_leave_amount=Decimal('1000'),
            cumulative_eosb_amount=Decimal('500'),
        )
        days, amount, text = settlement_leave_from_ledger(emp)
        self.assertEqual(days, Decimal('10'))
        self.assertEqual(amount, Decimal('1000'))
        self.assertIn('سجل المخصصات', text)


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

    def test_eosb_excludes_meal_allowance_base(self):
        from apps.employees.services.accrual_ledger_notes import compute_monthly_ledger_amounts

        calc = compute_monthly_ledger_amounts(
            gross_salary=Decimal('4300'),
            eosb_base=Decimal('4000'),
            hire_date=date(2026, 1, 1),
            period_year=2026,
            period_month=6,
        )
        self.assertEqual(calc['eosb'], Decimal('166.67'))
        self.assertEqual(calc['eosb_base'], Decimal('4000'))

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

    def test_structured_display_context_monthly(self):
        from apps.employees.models import EmployeeLedger
        from apps.employees.services.accrual_ledger_notes import get_ledger_display_context
        from apps.payroll.models import PayrollRun, PayrollLine
        from apps.core.models import Branch, Company

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', code='B1', company=company)
        emp = Employee.objects.create(name='موظف', basic_salary=Decimal('4000'), hire_date=date(2026, 1, 1))
        run = PayrollRun.objects.create(branch=branch, period_year=2026, period_month=6, status='locked')
        PayrollLine.objects.create(
            run=run, employee=emp, gross_salary=Decimal('4000'),
            daily_rate=Decimal('133.33'), month_days=30,
        )
        ledger = EmployeeLedger.objects.create(
            employee=emp,
            transaction_type=EmployeeLedger.TransactionType.MONTHLY_PAYROLL,
            date=date(2026, 6, 30),
            leave_days_change=Decimal('1.75'),
            leave_amount_change=Decimal('233.33'),
            eosb_amount_change=Decimal('166.67'),
            cumulative_leave_days=Decimal('3.47'),
            cumulative_leave_amount=Decimal('462.66'),
            cumulative_eosb_amount=Decimal('330.87'),
            payroll_run=run,
        )
        ctx = get_ledger_display_context(ledger)
        self.assertEqual(ctx['kind'], 'structured')
        self.assertEqual(len(ctx['sections']), 2)
        self.assertEqual(ctx['sections'][0]['id'], 'leave')

    def test_display_uses_30_days_not_stored_line_month_days(self):
        """حتى لو سطر المسير قديماً month_days=31، العرض والمعادلات على 30."""
        from apps.employees.models import EmployeeLedger
        from apps.employees.services.accrual_ledger_notes import get_ledger_display_context
        from apps.payroll.models import PayrollRun, PayrollLine
        from apps.core.models import Branch, Company

        company = Company.objects.create(name='شركة 2')
        branch = Branch.objects.create(name='فرع 2', code='B2', company=company)
        emp = Employee.objects.create(name='موظف 2', basic_salary=Decimal('4000'), hire_date=date(2026, 1, 1))
        run = PayrollRun.objects.create(branch=branch, period_year=2026, period_month=5, status='locked')
        PayrollLine.objects.create(
            run=run,
            employee=emp,
            gross_salary=Decimal('4000'),
            daily_rate=Decimal('129.03'),
            month_days=31,
        )
        ledger = EmployeeLedger.objects.create(
            employee=emp,
            transaction_type=EmployeeLedger.TransactionType.MONTHLY_PAYROLL,
            date=date(2026, 5, 31),
            leave_days_change=Decimal('1.75'),
            leave_amount_change=Decimal('225.80'),
            eosb_amount_change=Decimal('0'),
            cumulative_leave_days=Decimal('1.75'),
            cumulative_leave_amount=Decimal('225.80'),
            cumulative_eosb_amount=Decimal('0'),
            payroll_run=run,
        )
        ctx = get_ledger_display_context(ledger)
        leave_rows = ctx['sections'][0]['rows']
        daily_row = next(r for r in leave_rows if r['label'] == 'أجر اليوم')
        self.assertIn('÷ 30', daily_row['formula'])
        self.assertEqual(daily_row['result'], '133.33 ر.س')
        self.assertEqual(
            next(r for r in leave_rows if r['label'] == 'قيمة مخصص هذا الشهر')['result'],
            '233.33 ر.س',
        )
        self.assertEqual(
            next(m for m in ctx['meta'] if m['label'] == 'أيام الشهر')['value'],
            '30',
        )


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

    def test_last_installment_covers_loan_remainder(self):
        loan = EmployeeLoan.objects.create(
            employee=self.employee,
            amount=Decimal('1000.00'),
            monthly_deduction=Decimal('333.33'),
            installments=3,
            issued_at=date(2023, 1, 15),
            first_deduction_date=date(2023, 2, 1),
        )
        loan.generate_installments()
        total = sum(
            i.amount for i in loan.installments_log.all()
        )
        self.assertEqual(total, Decimal('1000.00'))
