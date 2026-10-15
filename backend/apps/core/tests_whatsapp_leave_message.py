"""رسالة واتساب للموظف بعد تنفيذ الإجازة يجب أن تتضمن تاريخي البداية والنهاية."""
from django.test import SimpleTestCase

from apps.core.models import PendingAction
from apps.core.services.whatsapp.templates import build_executed_message
from apps.employees.models import Employee


class LeaveExecutedMessageTests(SimpleTestCase):
    def _message(self, payload):
        action = PendingAction(
            action_type=PendingAction.ActionType.LEAVE,
            employee=Employee(name='عبدالله'),
            payload=payload,
        )
        return build_executed_message(action)

    def test_uses_leave_form_payload_keys(self):
        # نفس المفاتيح التي يحفظها add_employee_leave
        msg = self._message({'date_from': '2026-02-24', 'date_to': '2026-03-05'})
        self.assertIn('من: 2026-02-24', msg)
        self.assertIn('إلى: 2026-03-05', msg)

    def test_legacy_keys_still_supported(self):
        msg = self._message({'start_date': '2026-01-01', 'end_date': '2026-01-05'})
        self.assertIn('من: 2026-01-01', msg)
        self.assertIn('إلى: 2026-01-05', msg)
