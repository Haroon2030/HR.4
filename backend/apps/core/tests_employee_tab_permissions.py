"""اختبارات تبويبات ملف الموظف."""
from django.test import SimpleTestCase

from apps.core.employee_tab_permissions import EDIT_FORM_TAB_KEYS


class EditFormTabKeysTests(SimpleTestCase):
    def test_edit_form_excludes_operation_tabs(self):
        self.assertNotIn('warnings', EDIT_FORM_TAB_KEYS)
        self.assertNotIn('archive', EDIT_FORM_TAB_KEYS)

    def test_edit_form_keeps_core_data_tabs(self):
        for key in ('main', 'contract', 'salary', 'leaves', 'schedule', 'docs'):
            self.assertIn(key, EDIT_FORM_TAB_KEYS)
