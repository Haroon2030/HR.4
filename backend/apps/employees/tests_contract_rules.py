from datetime import date

from django.test import TestCase

from apps.employees.models import Employee
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.employees.services.contract_rules import (
    ContractType,
    compute_contract_expiry,
    fourth_year_start,
    is_saudi_nationality,
    is_valid_saudi_insurance_rate,
    should_auto_unlimited,
    sync_employee_contract,
    validate_contract_fields,
    validate_insurance_deduction_rate_for_nationality,
)
from apps.setup.models import Nationality


class ContractRulesTests(TestCase):
    def setUp(self):
        self.saudi = Nationality.objects.create(name='سعودي', code='SA')
        self.foreign = Nationality.objects.create(name='مصري', code='EG')

    def test_is_saudi_by_code_and_name(self):
        self.assertTrue(is_saudi_nationality(self.saudi))
        self.assertFalse(is_saudi_nationality(self.foreign))
        self.assertFalse(is_saudi_nationality(None))

    def test_saudi_insurance_rates_whitelist(self):
        self.assertTrue(is_valid_saudi_insurance_rate(Decimal('10.75')))
        self.assertTrue(is_valid_saudi_insurance_rate('10.25'))
        self.assertFalse(is_valid_saudi_insurance_rate(Decimal('10')))
        validate_insurance_deduction_rate_for_nationality(Decimal('9.75'), self.saudi)
        with self.assertRaises(ValidationError):
            validate_insurance_deduction_rate_for_nationality(Decimal('10'), self.saudi)
        validate_insurance_deduction_rate_for_nationality(Decimal('15'), self.foreign)

    def test_fourth_year_start(self):
        self.assertEqual(fourth_year_start(date(2020, 3, 15)), date(2023, 3, 15))

    def test_should_auto_unlimited_saudi_after_three_years(self):
        hire = date(2020, 1, 1)
        self.assertFalse(should_auto_unlimited(hire_date=hire, nationality=self.saudi, today=date(2022, 12, 31)))
        self.assertTrue(should_auto_unlimited(hire_date=hire, nationality=self.saudi, today=date(2023, 1, 1)))

    def test_sync_auto_unlimited_clears_fixed_fields(self):
        emp = Employee(
            hire_date=date(2019, 1, 1),
            nationality=self.saudi,
            contract_type=ContractType.FIXED,
            contract_duration_months=12,
            contract_duration_text='سنة',
            contract_expiry_date=date(2025, 1, 1),
        )
        changed = sync_employee_contract(emp, today=date(2023, 6, 1))
        self.assertTrue(changed)
        self.assertEqual(emp.contract_type, ContractType.UNLIMITED)
        self.assertIsNone(emp.contract_duration_months)
        self.assertEqual(emp.contract_duration_text, '')
        self.assertIsNone(emp.contract_expiry_date)

    def test_sync_computes_expiry_for_saudi_fixed(self):
        emp = Employee(
            nationality=self.saudi,
            hire_date=date(2024, 1, 1),
            contract_type=ContractType.FIXED,
            contract_start_date=date(2024, 1, 1),
            contract_duration_months=12,
        )
        changed = sync_employee_contract(emp, today=date(2024, 6, 1))
        self.assertTrue(changed)
        self.assertEqual(emp.contract_expiry_date, compute_contract_expiry(date(2024, 1, 1), 12))

    def test_validate_saudi_duration_max_12(self):
        errors = validate_contract_fields(
            nationality=self.saudi,
            hire_date=date(2024, 1, 1),
            contract_type=ContractType.FIXED,
            contract_duration_months=13,
            contract_duration_text='',
            contract_start_date=date(2024, 1, 1),
            contract_expiry_date=None,
        )
        self.assertIn('contract_duration_months', errors)

    def test_validate_foreign_requires_duration_text(self):
        errors = validate_contract_fields(
            nationality=self.foreign,
            hire_date=date(2024, 1, 1),
            contract_type=ContractType.FIXED,
            contract_duration_months=None,
            contract_duration_text='',
            contract_start_date=date(2024, 1, 1),
            contract_expiry_date=None,
        )
        self.assertIn('contract_duration_text', errors)
