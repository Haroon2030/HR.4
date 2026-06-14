from django.test import SimpleTestCase

from apps.employees.status_ui import (
    EMPLOYEE_STATUS_ORDER,
    build_employee_status_dashboard_rows,
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
        self.assertEqual(rows[1]['icon'], 'calendar-off')
        self.assertEqual(rows[3]['color'], 'terminated')

    def test_build_dashboard_rows_empty_total(self):
        rows = build_employee_status_dashboard_rows({'employees_total': 0})
        self.assertTrue(all(row['percent'] == 0 for row in rows))

    def test_dist_palette_matches_status_colors(self):
        palette = employee_status_dist_palette()
        self.assertEqual(palette[:4], tuple(get_employee_status_ui(s).color for s in EMPLOYEE_STATUS_ORDER))
