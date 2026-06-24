"""اختبارات ترحيل الأرصدة الافتتاحية."""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.core.models import Branch, Company
from apps.employees.models import Employee, EmployeeLeave
from apps.employees.services.leave_balance import (
    compute_employee_accrued_leave_days,
    compute_employee_remaining_leave_days,
    leave_balance_breakdown,
    settlement_leave_for_employee,
)
from apps.employees.services.migration_balance import should_accrue_leave_in_period
from apps.employees.services.opening_balances import apply_opening_balance_to_employee
from apps.setup.models import Sponsorship


@override_settings(HR_MIGRATION_CUTOVER_DATE='2026-07-01')
class MigrationOpeningBalanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة ترحيل', commercial_record='1')
        cls.branch = Branch.objects.create(name='الفرع', code='MIG', company=cls.company)
        cls.sponsorship = Sponsorship.objects.create(
            code='SP-MIG',
            company_name='كفالة ترحيل',
            commercial_registration='999',
        )

    def _create_employee(self, **kwargs):
        defaults = {
            'name': 'موظف ترحيل',
            'branch': self.branch,
            'sponsorship': self.sponsorship,
            'hire_date': date(2019, 3, 1),
            'basic_salary': Decimal('6000.00'),
            'housing_allowance': Decimal('1000.00'),
            'status': Employee.Status.ACTIVE,
        }
        defaults.update(kwargs)
        return Employee.objects.create(**defaults)

    def test_apply_opening_balance_sets_migration_fields(self):
        emp = self._create_employee()
        apply_opening_balance_to_employee(
            emp,
            opening_leave_days=Decimal('18'),
            opening_eosb_amount=Decimal('45000'),
            cutover_date=date(2026, 7, 1),
        )
        emp.refresh_from_db()
        self.assertTrue(emp.migration_locked)
        self.assertEqual(emp.opening_leave_days, Decimal('18.00'))
        self.assertEqual(emp.opening_eosb_amount, Decimal('45000.00'))
        self.assertEqual(emp.leave_accrual_start_date, date(2026, 7, 1))
        self.assertEqual(emp.accruals_ledger.count(), 1)

    def test_accrued_leave_is_opening_plus_period_not_from_hire_date(self):
        emp = self._create_employee()
        apply_opening_balance_to_employee(
            emp,
            opening_leave_days=Decimal('18'),
            opening_eosb_amount=Decimal('0'),
            cutover_date=date(2026, 7, 1),
        )
        emp.refresh_from_db()
        as_of = date(2026, 12, 1)
        accrued = compute_employee_accrued_leave_days(emp, as_of=as_of)
        # 18 افتتاحي + 5 أشهر × 1.75 = 8.75
        self.assertEqual(accrued, Decimal('26.75'))
        self.assertGreater(accrued, Decimal('18'))

    def test_used_leave_only_counts_after_cutover(self):
        emp = self._create_employee()
        apply_opening_balance_to_employee(
            emp,
            opening_leave_days=Decimal('18'),
            opening_eosb_amount=Decimal('0'),
            cutover_date=date(2026, 7, 1),
        )
        EmployeeLeave.objects.create(
            employee=emp,
            leave_type=EmployeeLeave.LeaveType.ANNUAL,
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 5),
            days=Decimal('5'),
        )
        remaining = compute_employee_remaining_leave_days(emp, as_of=date(2026, 12, 1))
        self.assertEqual(remaining, Decimal('21.75'))

    def test_settlement_leave_mentions_hire_date_for_eosb(self):
        emp = self._create_employee()
        apply_opening_balance_to_employee(
            emp,
            opening_leave_days=Decimal('10'),
            opening_eosb_amount=Decimal('1000'),
            cutover_date=date(2026, 7, 1),
        )
        _, _, _, _, text = settlement_leave_for_employee(emp, as_of=date(2026, 12, 15))
        self.assertIn('2019-03-01', text)
        self.assertIn('رصيد افتتاحي', text)

    def test_should_not_accrue_leave_before_cutover_month(self):
        emp = self._create_employee()
        apply_opening_balance_to_employee(
            emp,
            opening_leave_days=Decimal('5'),
            opening_eosb_amount=Decimal('0'),
            cutover_date=date(2026, 7, 1),
        )
        emp.refresh_from_db()
        self.assertFalse(should_accrue_leave_in_period(emp, 2026, 6))
        self.assertTrue(should_accrue_leave_in_period(emp, 2026, 7))

    def test_leave_balance_breakdown_structure(self):
        emp = self._create_employee()
        apply_opening_balance_to_employee(
            emp,
            opening_leave_days=Decimal('12'),
            opening_eosb_amount=Decimal('5000'),
            cutover_date=date(2026, 7, 1),
        )
        bd = leave_balance_breakdown(emp, as_of=date(2026, 10, 1))
        self.assertTrue(bd['uses_migration'])
        self.assertEqual(bd['opening_days'], Decimal('12.00'))
        self.assertEqual(bd['leave_accrual_start'], date(2026, 7, 1))
        self.assertEqual(bd['hire_date'], date(2019, 3, 1))

    def test_manual_opening_fields_without_migration_lock(self):
        emp = self._create_employee(
            leave_accrual_start_date=date(2026, 7, 1),
            opening_leave_days=Decimal('15'),
        )
        self.assertFalse(emp.migration_locked)
        accrued = compute_employee_accrued_leave_days(emp, as_of=date(2026, 12, 1))
        self.assertEqual(accrued, Decimal('23.75'))

    def test_cannot_reimport_without_replace(self):
        emp = self._create_employee()
        apply_opening_balance_to_employee(
            emp,
            opening_leave_days=Decimal('8'),
            opening_eosb_amount=Decimal('0'),
            cutover_date=date(2026, 7, 1),
        )
        with self.assertRaises(ValueError):
            apply_opening_balance_to_employee(
                emp,
                opening_leave_days=Decimal('9'),
                opening_eosb_amount=Decimal('0'),
                cutover_date=date(2026, 7, 1),
            )
