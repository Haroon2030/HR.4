from django.http import QueryDict
from django.test import TestCase
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from apps.employees.forms import EmployeeForm, EmploymentRequestEditForm
from apps.employees.models import Employee, EmployeeAbsence, EmployeeLoan, EmployeeLedger, LoanInstallment, EmploymentRequest
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
        """12 شهر خدمة = 12 × 1.75 = 21 يوم مستحق."""
        self.employee.end_date = date(2024, 1, 1)
        self.assertEqual(self.employee.accrued_leave_days, Decimal('21.00'))

    def test_accrued_leave_days_eighteen_months(self):
        """18 شهر = 31.5 يوم — يطابق المعدل الشهري 21÷12."""
        self.employee.hire_date = date(2024, 12, 22)
        self.employee.end_date = date(2026, 6, 22)
        self.assertEqual(self.employee.accrued_leave_days, Decimal('31.50'))

    def test_remaining_leave_eighteen_months_minus_twenty_one_used(self):
        """سيناريو المستخدم: 31.5 مستحق − 21 مستخدم = 10.5 متبقي."""
        from apps.employees.models import EmployeeLeave

        self.employee.hire_date = date(2024, 12, 22)
        self.employee.end_date = date(2026, 6, 22)
        EmployeeLeave.objects.create(
            employee=self.employee,
            leave_type=EmployeeLeave.LeaveType.ANNUAL,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 21),
            days=Decimal('21'),
        )
        self.assertEqual(self.employee.accrued_leave_days, Decimal('31.50'))
        self.assertEqual(self.employee.used_leave_days, Decimal('21.00'))
        self.assertEqual(self.employee.remaining_leave_days, Decimal('10.50'))

    def test_accrued_leave_days_tiered_after_five_years(self):
        """بعد 5 سنوات: 105 يوم + 2.5 يوم/شهر × الأشهر الزائدة."""
        self.employee.hire_date = date(2017, 1, 1)
        self.employee.end_date = date(2024, 1, 1)  # 84 شهر
        expected = Decimal('165.00')  # 60×1.75 + 24×2.5
        self.assertEqual(self.employee.accrued_leave_days, expected)

    def test_remaining_leave_days(self):
        """المتبقي = المستحق − المستخدم (12 شهر − 5 مستخدمة)."""
        self.employee.end_date = date(2024, 1, 1)
        self.assertEqual(self.employee.remaining_leave_days, Decimal('16.00'))

    def test_used_leave_days_from_annual_records(self):
        from apps.employees.models import EmployeeLeave

        EmployeeLeave.objects.create(
            employee=self.employee,
            leave_type=EmployeeLeave.LeaveType.ANNUAL,
            date_from=date(2023, 6, 1),
            date_to=date(2023, 6, 5),
            days=Decimal('5'),
        )
        self.employee.available_leave_balance = Decimal('2')
        self.assertEqual(self.employee.used_leave_days, Decimal('5.00'))

    def test_leave_compensation(self):
        """Test leave compensation (remaining_leave_days * daily_wage)"""
        self.employee.end_date = date(2024, 1, 1)
        expected_compensation = (Decimal('16.00') * self.employee.daily_wage).quantize(Decimal('0.01'))
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
    def test_settlement_uses_formula_not_ledger_cumulative(self):
        """التصفية تعتمد الصيغة الموحدة (أشهر × 1.75) وليس تراكم الدفتر."""
        from apps.employees.models import EmployeeLedger
        from apps.employees.services.ledger_balances import settlement_leave_from_ledger
        from apps.setup.models import Sponsorship

        sponsorship = Sponsorship.objects.create(code='SP-L', company_name='K')
        emp = Employee.objects.create(
            name='Ledger Emp',
            hire_date=date(2024, 1, 1),
            end_date=date(2025, 1, 1),
            sponsorship=sponsorship,
            basic_salary=Decimal('3000'),
            available_leave_balance=Decimal('5'),
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
        self.assertEqual(days, Decimal('16.00'))  # 21 مستحق − 5 مستخدم
        expected_amount = (Decimal('16') * (Decimal('3000') / Decimal('30'))).quantize(Decimal('0.01'))
        self.assertEqual(amount, expected_amount)
        self.assertIn('1.75', text)


class LedgerRecalculateTests(TestCase):
    def test_recalc_initial_only_wrong_formula(self):
        from apps.employees.services.ledger_recalculate import recalculate_employee_ledger
        from apps.setup.models import Sponsorship

        sponsorship = Sponsorship.objects.create(code='SP-R', company_name='K')
        emp = Employee.objects.create(
            name='Recalc Emp',
            hire_date=date(2024, 12, 22),
            sponsorship=sponsorship,
            basic_salary=Decimal('6000'),
        )
        ledger = EmployeeLedger.objects.create(
            employee=emp,
            transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
            date=date(2026, 6, 22),
            leave_days_change=Decimal('31.33'),
            leave_amount_change=Decimal('6266.00'),
            cumulative_leave_days=Decimal('31.33'),
            cumulative_leave_amount=Decimal('6266.00'),
            cumulative_eosb_amount=Decimal('0'),
        )
        result = recalculate_employee_ledger(emp)
        ledger.refresh_from_db()
        self.assertEqual(result.entries_updated, 1)
        self.assertEqual(ledger.cumulative_leave_days, Decimal('31.5000'))
        self.assertIn('1.75', ledger.notes)

    def test_recalc_removes_redundant_initial_when_monthly_exists(self):
        from apps.core.salary_month import calendar_month_last_day
        from apps.employees.services.ledger_recalculate import recalculate_employee_ledger
        from apps.payroll.models import PayrollLine, PayrollRun
        from apps.core.models import Branch, Company
        from apps.setup.models import Sponsorship

        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        sponsorship = Sponsorship.objects.create(code='SP-M', company_name='K')
        emp = Employee.objects.create(
            name='Monthly Emp',
            hire_date=date(2024, 12, 22),
            sponsorship=sponsorship,
            branch=branch,
            basic_salary=Decimal('3000'),
        )
        run = PayrollRun.objects.create(
            branch=branch,
            period_year=2025,
            period_month=1,
            status='locked',
        )
        PayrollLine.objects.create(
            run=run,
            employee=emp,
            gross_salary=Decimal('3000'),
            meal_allowance=Decimal('0'),
            month_days=30,
            daily_rate=Decimal('100'),
            net_salary=Decimal('3000'),
        )
        EmployeeLedger.objects.create(
            employee=emp,
            transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
            date=date(2026, 6, 22),
            leave_days_change=Decimal('31.33'),
            leave_amount_change=Decimal('3133'),
            cumulative_leave_days=Decimal('31.33'),
            cumulative_leave_amount=Decimal('3133'),
            cumulative_eosb_amount=Decimal('0'),
        )
        monthly = EmployeeLedger.objects.create(
            employee=emp,
            transaction_type=EmployeeLedger.TransactionType.MONTHLY_PAYROLL,
            date=calendar_month_last_day(2025, 1),
            payroll_run=run,
            leave_days_change=Decimal('1.75'),
            leave_amount_change=Decimal('175'),
            cumulative_leave_days=Decimal('33.08'),
            cumulative_leave_amount=Decimal('3308'),
            cumulative_eosb_amount=Decimal('125'),
        )
        result = recalculate_employee_ledger(emp)
        monthly.refresh_from_db()
        self.assertEqual(result.entries_removed, 1)
        self.assertEqual(result.entries_updated, 1)
        self.assertEqual(monthly.cumulative_leave_days, Decimal('1.7500'))
        self.assertFalse(
            EmployeeLedger.objects.filter(
                employee=emp,
                transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
            ).exists(),
        )


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


class SettlementEosbCalculationTests(TestCase):
    def test_first_five_years_half_salary(self):
        from apps.employees.services.settlement_eosb import compute_settlement_eosb

        before, after, category, note = compute_settlement_eosb(
            last_salary=Decimal('6000'),
            service_days=365 * 3,
            service_years=Decimal('3'),
            settlement_type='contract_expiry',
            eligible=True,
        )
        self.assertEqual(before, Decimal('9000.00'))
        self.assertEqual(after, Decimal('9000.00'))
        self.assertIn('½ راتب', category)
        self.assertEqual(note, '')

    def test_after_five_years_full_salary_for_extra_years(self):
        from apps.employees.services.settlement_eosb import compute_settlement_eosb

        before, after, category, note = compute_settlement_eosb(
            last_salary=Decimal('6000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            settlement_type='contract_expiry',
            eligible=True,
        )
        self.assertEqual(before, Decimal('27000.00'))
        self.assertEqual(after, Decimal('27000.00'))
        self.assertIn('راتب كامل', category)
        self.assertEqual(note, '')

    def test_resignation_applies_only_for_employee_type(self):
        from apps.employees.services.settlement_eosb import compute_settlement_eosb

        _, after, _, note = compute_settlement_eosb(
            last_salary=Decimal('6000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            settlement_type='employee',
            eligible=True,
        )
        self.assertEqual(after, Decimal('18000.00'))
        self.assertIn('ثلثي', note)

    def test_article_77_company_full_eosb_with_penalty(self):
        from apps.employees.services.settlement_eosb import (
            compute_settlement_eosb,
            compute_two_month_penalty,
        )

        before, after, _, _ = compute_settlement_eosb(
            last_salary=Decimal('6000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            settlement_type='article_77',
            eligible=True,
            article_77_party='company',
        )
        self.assertEqual(before, after)
        self.assertEqual(before, Decimal('27000.00'))
        self.assertEqual(compute_two_month_penalty(Decimal('7000')), Decimal('14000.00'))

    def test_article_77_employee_resignation_with_penalty(self):
        from apps.employees.services.settlement_eosb import compute_settlement_eosb

        _, after, _, note = compute_settlement_eosb(
            last_salary=Decimal('6000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            settlement_type='article_77',
            eligible=True,
            article_77_party='employee',
        )
        self.assertEqual(after, Decimal('18000.00'))
        self.assertIn('ثلثي', note)

    def test_tiered_leave_first_five_years(self):
        from apps.employees.services.settlement_eosb import compute_tiered_leave_accrued_days

        days = compute_tiered_leave_accrued_days(int(365.25 * 3))
        self.assertEqual(days, Decimal('63.88'))

    def test_tiered_leave_after_five_years(self):
        from apps.employees.services.settlement_eosb import compute_tiered_leave_accrued_days

        days = compute_tiered_leave_accrued_days(int(365.25 * 7))
        self.assertEqual(days, Decimal('168.00'))

    def test_article_80_leave_settlement_only(self):
        from apps.core.models import Branch, Company
        from apps.employees.services.settlement_eosb import compute_article_80_leave_settlement
        from apps.setup.models import Sponsorship

        sponsorship = Sponsorship.objects.create(code='SP-80', company_name='K')
        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        emp = Employee.objects.create(
            name='موظف 80',
            hire_date=date(2017, 1, 1),
            sponsorship=sponsorship,
            branch=branch,
            basic_salary=Decimal('6000'),
        )
        remaining, amount, text = compute_article_80_leave_settlement(
            employee=emp,
            as_of=date(2024, 1, 1),
        )
        self.assertEqual(remaining, Decimal('165.00'))
        self.assertGreater(amount, Decimal('0'))
        self.assertIn('2.5', text)

    def test_article_80_eosb_is_zero(self):
        from apps.employees.services.settlement_eosb import compute_settlement_eosb

        before, after, category, _ = compute_settlement_eosb(
            last_salary=Decimal('6000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            settlement_type='article_80',
            eligible=True,
        )
        self.assertEqual(before, Decimal('0'))
        self.assertEqual(after, Decimal('0'))
        self.assertIn('المادة 80', category)

    def test_probation_end_leave_settlement_flat_21(self):
        from apps.core.models import Branch, Company
        from apps.employees.services.settlement_eosb import compute_probation_end_leave_settlement
        from apps.setup.models import Sponsorship

        sponsorship = Sponsorship.objects.create(code='SP-PR', company_name='K')
        company = Company.objects.create(name='شركة')
        branch = Branch.objects.create(name='فرع', company=company)
        emp = Employee.objects.create(
            name='تجربة',
            hire_date=date(2017, 1, 1),
            sponsorship=sponsorship,
            branch=branch,
            basic_salary=Decimal('6000'),
        )
        remaining, amount, text = compute_probation_end_leave_settlement(
            employee=emp,
            as_of=date(2024, 1, 1),
        )
        self.assertEqual(remaining, Decimal('147.00'))
        self.assertGreater(amount, Decimal('0'))
        self.assertIn('1.75', text)
        self.assertNotIn('2.5', text)

    def test_probation_end_eosb_is_zero(self):
        from apps.employees.services.settlement_eosb import compute_settlement_eosb

        before, after, category, _ = compute_settlement_eosb(
            last_salary=Decimal('6000'),
            service_days=90,
            service_years=Decimal('0.25'),
            settlement_type='probation_end',
            eligible=True,
        )
        self.assertEqual(before, Decimal('0'))
        self.assertEqual(after, Decimal('0'))
        self.assertIn('نهاية فترة التجربة', category)

    def test_article_74_company_matches_standard_eosb(self):
        from apps.employees.services.settlement_eosb import (
            compute_article_74_eosb,
            compute_standard_eosb,
        )

        std, _ = compute_standard_eosb(
            last_salary=Decimal('6000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            eligible=True,
        )
        art74, _ = compute_article_74_eosb(
            last_salary=Decimal('6000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            party='company',
            eligible=True,
        )
        self.assertEqual(std, art74)

    def test_article_74_employee_third_and_two_thirds(self):
        from apps.employees.services.settlement_eosb import compute_article_74_eosb

        eosb, category = compute_article_74_eosb(
            last_salary=Decimal('6000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            party='employee',
            eligible=True,
        )
        first_5 = (Decimal('6000') / 3 * 5).quantize(Decimal('0.01'))
        extra = (Decimal('6000') * Decimal('2') / Decimal('3') * Decimal('2')).quantize(Decimal('0.01'))
        self.assertEqual(eosb, first_5 + extra)
        self.assertIn('⅔ راتب', category)

    def test_article_74_employee_salary_3000_example(self):
        """راتب 3000 → ⅓=1000/سنة، ⅔=2000/سنة."""
        from apps.employees.services.settlement_eosb import compute_article_74_eosb

        eosb, category = compute_article_74_eosb(
            last_salary=Decimal('3000'),
            service_days=int(365.25 * 7),
            service_years=Decimal('7'),
            party='employee',
            eligible=True,
        )
        self.assertEqual(eosb, Decimal('9000.00'))
        self.assertIn('1000.00', category)
        self.assertIn('2000.00', category)
