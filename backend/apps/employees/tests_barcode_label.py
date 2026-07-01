from django.test import TestCase

from apps.core.models import Branch, Company
from apps.employees.models import Employee
from apps.employees.services.barcode_label import (
    DEFAULT_LABEL_HEIGHT_MM,
    DEFAULT_LABEL_WIDTH_MM,
    barcode_value_for_employee,
    build_employee_barcode_label,
    build_zpl_label,
    parse_copies,
    parse_label_dimensions,
    sponsorship_company_for_employee,
)
from apps.setup.models import Sponsorship


class BarcodeLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة اختبار')
        cls.branch = Branch.objects.create(name='فرع 1', code='B1', company=company)
        cls.sponsorship = Sponsorship.objects.create(
            code='SP-01',
            company_name='شركة الرشيد للتجارة',
        )
        cls.employee = Employee.objects.create(
            name='أحمد محمد',
            employee_number='EMP-1001',
            branch=cls.branch,
            sponsorship=cls.sponsorship,
        )

    def test_barcode_value_prefers_employee_number(self):
        self.assertEqual(barcode_value_for_employee(self.employee), 'EMP-1001')

    def test_sponsorship_company_name(self):
        self.assertEqual(
            sponsorship_company_for_employee(self.employee),
            'شركة الرشيد للتجارة',
        )

    def test_build_label_company_and_number(self):
        dims = parse_label_dimensions(80, 30)
        label = build_employee_barcode_label(self.employee, dims=dims)
        self.assertEqual(label.company_name, 'شركة الرشيد للتجارة')
        self.assertEqual(label.number_display, 'EMP-1001')
        self.assertEqual(label.name, 'أحمد محمد')

    def test_company_falls_back_to_branch_company(self):
        emp = Employee.objects.create(
            name='بدون كفالة',
            employee_number='99',
            branch=self.branch,
        )
        label = build_employee_barcode_label(emp)
        self.assertEqual(label.company_name, 'شركة اختبار')

    def test_parse_label_dimensions_clamps(self):
        dims = parse_label_dimensions('200', '5')
        self.assertEqual(dims.width_mm, 150.0)
        self.assertEqual(dims.height_mm, 15.0)

    def test_zpl_scales_with_dimensions(self):
        label = build_employee_barcode_label(self.employee)
        small = parse_label_dimensions(50, 25)
        zpl = build_zpl_label(label, dims=small, copies=1)
        self.assertIn(f'^PW{small.width_dots}', zpl)
        self.assertIn(f'^LL{small.height_dots}', zpl)

    def test_zpl_name_company_and_number(self):
        label = build_employee_barcode_label(self.employee)
        dims = parse_label_dimensions(DEFAULT_LABEL_WIDTH_MM, DEFAULT_LABEL_HEIGHT_MM)
        zpl = build_zpl_label(label, dims=dims, copies=2)
        self.assertIn('أحمد محمد', zpl)
        self.assertIn('شركة الرشيد للتجارة', zpl)
        self.assertIn('EMP-1001', zpl)
        self.assertIn('^FB', zpl)
        self.assertNotIn('^BCN', zpl)
        self.assertIn('^PQ2', zpl)

    def test_parse_copies_bounds(self):
        self.assertEqual(parse_copies('3'), 3)
        self.assertEqual(parse_copies('0'), 1)
        self.assertEqual(parse_copies('99'), 50)
        self.assertEqual(parse_copies('x', default=2), 2)
