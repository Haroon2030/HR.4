from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.core.services.email_recipients import (
    allowed_hr_recipients,
    resolve_statement_email_recipients,
)

User = get_user_model()


class EmailRecipientsTests(TestCase):
    @override_settings(
        DEFAULT_FROM_EMAIL='noreply@company.test',
        HR_NOTIFICATION_EMAIL='hr@company.test',
    )
    def test_employee_email_used_when_posted_empty(self):
        employee = SimpleNamespace(email='emp@company.test')
        actor = SimpleNamespace(email='admin@company.test')
        recipients = resolve_statement_email_recipients(
            employee,
            posted_employee_email='',
            posted_hr_email='',
            actor=actor,
        )
        self.assertIn('emp@company.test', recipients)
        self.assertIn('hr@company.test', recipients)

    @override_settings(
        DEFAULT_FROM_EMAIL='noreply@company.test',
        HR_NOTIFICATION_EMAIL='',
    )
    def test_hr_fallback_to_actor_when_no_hr_setting(self):
        employee = SimpleNamespace(email='')
        actor = SimpleNamespace(email='admin@company.test')
        recipients = resolve_statement_email_recipients(
            employee,
            posted_employee_email='',
            posted_hr_email='',
            actor=actor,
        )
        self.assertEqual(recipients, ['admin@company.test'])

    @override_settings(
        DEFAULT_FROM_EMAIL='noreply@company.test',
        HR_NOTIFICATION_EMAIL='hr@company.test',
    )
    def test_rejects_mismatched_employee_email(self):
        employee = SimpleNamespace(email='emp@company.test')
        actor = SimpleNamespace(email='admin@company.test')
        recipients = resolve_statement_email_recipients(
            employee,
            posted_employee_email='other@evil.test',
            posted_hr_email='hr@company.test',
            actor=actor,
        )
        self.assertNotIn('other@evil.test', recipients)
        self.assertNotIn('emp@company.test', recipients)
        self.assertIn('hr@company.test', recipients)

    @override_settings(
        DEFAULT_FROM_EMAIL='noreply@company.test',
        HR_NOTIFICATION_EMAIL='hr@company.test',
    )
    def test_posted_hr_must_be_allowed(self):
        employee = SimpleNamespace(email='emp@company.test')
        actor = SimpleNamespace(email='admin@company.test')
        recipients = resolve_statement_email_recipients(
            employee,
            posted_employee_email='emp@company.test',
            posted_hr_email='stranger@evil.test',
            actor=actor,
        )
        self.assertNotIn('stranger@evil.test', recipients)
        self.assertIn('emp@company.test', recipients)
        self.assertIn('hr@company.test', recipients)

    @override_settings(
        DEFAULT_FROM_EMAIL='noreply@company.test',
        HR_NOTIFICATION_EMAIL='hr@company.test',
    )
    def test_allowed_hr_recipients_includes_defaults(self):
        actor = SimpleNamespace(email='admin@company.test')
        allowed = allowed_hr_recipients(actor)
        self.assertIn('noreply@company.test', allowed)
        self.assertIn('hr@company.test', allowed)
        self.assertIn('admin@company.test', allowed)
