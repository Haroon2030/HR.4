from django.test import SimpleTestCase

from apps.employees.status_ui import (
    EMPLOYEE_STATUS_ORDER,
    build_employee_status_dashboard_rows,
    build_employee_status_donut_style,
    employee_status_dist_palette,
    get_employee_status_ui,
)


class EmployeeStatusUITests(SimpleTestCase):
    def test_all_statuses_have_metadata(self):
        for status in EMPLOYEE_STATUS_ORDER:
            ui = get_employee_status_ui(status)
            self.assertEqual(ui.status, status)
            self.assertTrue(ui.label)
            self.assertTrue(ui.icon)
            self.assertTrue(ui.color)
            self.assertTrue(ui.stats_key)
            self.assertTrue(ui.badge_class)

    def test_unknown_status_fallback(self):
        ui = get_employee_status_ui('unknown')
        self.assertEqual(ui.label, 'غير محدد')
        self.assertEqual(ui.icon, 'user')

    def test_build_dashboard_rows_percentages(self):
        stats = {
            'employees_total': 10,
            'employees_active': 5,
            'employees_leave': 2,
            'employees_suspended': 1,
            'employees_terminated': 2,
        }
        rows = build_employee_status_dashboard_rows(stats)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['count'], 5)
        self.assertEqual(rows[0]['percent'], 50)
        self.assertEqual(rows[0]['theme'], 'emerald')
        self.assertEqual(rows[1]['icon'], 'calendar-off')
        self.assertEqual(rows[3]['color'], 'terminated')

    def test_build_dashboard_rows_empty_total(self):
        rows = build_employee_status_dashboard_rows({'employees_total': 0})
        self.assertTrue(all(row['percent'] == 0 for row in rows))

    def test_build_donut_style_segments(self):
        rows = build_employee_status_dashboard_rows(
            {
                'employees_total': 10,
                'employees_active': 5,
                'employees_leave': 2,
                'employees_suspended': 1,
                'employees_terminated': 2,
            }
        )
        style = build_employee_status_donut_style(rows)
        self.assertIn('conic-gradient', style)
        self.assertIn('#10b981', style)
        self.assertIn('#f43f5e', style)

    def test_build_donut_style_single_segment(self):
        rows = build_employee_status_dashboard_rows(
            {
                'employees_total': 3,
                'employees_active': 3,
                'employees_leave': 0,
                'employees_suspended': 0,
                'employees_terminated': 0,
            }
        )
        style = build_employee_status_donut_style(rows)
        self.assertIn('#10b981 0.00deg 360.00deg', style)

    def test_build_donut_style_empty(self):
        style = build_employee_status_donut_style([])
        self.assertEqual(style, 'conic-gradient(#e2e8f0 0deg 360deg)')

    def test_dist_palette_matches_status_colors(self):
        palette = employee_status_dist_palette()
        self.assertEqual(palette[:4], tuple(get_employee_status_ui(s).color for s in EMPLOYEE_STATUS_ORDER))
