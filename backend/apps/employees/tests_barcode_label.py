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
)


class BarcodeLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة اختبار')
        cls.branch = Branch.objects.create(name='فرع 1', code='B1', company=company)
        cls.employee = Employee.objects.create(
            name='أحمد محمد',
            employee_number='EMP-1001',
            branch=cls.branch,
        )

    def test_barcode_value_prefers_employee_number(self):
        self.assertEqual(barcode_value_for_employee(self.employee), 'EMP-1001')

    def test_build_label_includes_svg(self):
        dims = parse_label_dimensions(80, 30)
        label = build_employee_barcode_label(self.employee, dims=dims)
        self.assertEqual(label.name, 'أحمد محمد')
        self.assertEqual(label.number_display, 'EMP-1001')
        self.assertIn('<svg', label.barcode_svg)
        self.assertIn('</svg>', label.barcode_svg)

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

    def test_zpl_contains_barcode_command(self):
        label = build_employee_barcode_label(self.employee)
        dims = parse_label_dimensions(DEFAULT_LABEL_WIDTH_MM, DEFAULT_LABEL_HEIGHT_MM)
        zpl = build_zpl_label(label, dims=dims, copies=2)
        self.assertIn('^BCN', zpl)
        self.assertIn('EMP-1001', zpl)
        self.assertIn('^PQ2', zpl)

    def test_parse_copies_bounds(self):
        self.assertEqual(parse_copies('3'), 3)
        self.assertEqual(parse_copies('0'), 1)
        self.assertEqual(parse_copies('99'), 50)
        self.assertEqual(parse_copies('x', default=2), 2)
