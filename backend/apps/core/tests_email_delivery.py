"""اختبارات ضبط المرسل ورسائل SMTP."""
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from apps.core.services.email_delivery import (
    email_delivery_status,
    from_email_smtp_mismatch_warning,
    prepare_outbound_message,
    resolve_from_email,
)


class ResolveFromEmailTests(SimpleTestCase):
    @override_settings(
        EMAIL_HOST_USER='hr@alrsheed.net',
        DEFAULT_FROM_EMAIL='HR Pro <wrong@other.com>',
    )
    def test_resolve_from_email_uses_smtp_user_with_display_name(self):
        self.assertEqual(resolve_from_email(), 'HR Pro <hr@alrsheed.net>')

    @override_settings(
        EMAIL_HOST_USER='hr@alrsheed.net',
        DEFAULT_FROM_EMAIL='hr@alrsheed.net',
    )
    def test_resolve_from_email_plain_user(self):
        self.assertEqual(resolve_from_email(), 'hr@alrsheed.net')

    @override_settings(EMAIL_HOST_USER='', DEFAULT_FROM_EMAIL='noreply@localhost')
    def test_resolve_from_email_fallback_without_smtp_user(self):
        self.assertEqual(resolve_from_email(), 'noreply@localhost')


class PrepareOutboundMessageTests(SimpleTestCase):
    @override_settings(
        EMAIL_HOST_USER='hr@alrsheed.net',
        DEFAULT_FROM_EMAIL='HR Pro <hr@alrsheed.net>',
    )
    def test_prepare_sets_reply_to(self):
        msg = EmailMessage(subject='test', body='body', to=['a@b.com'])
        msg.from_email = 'wrong@other.com'
        prepare_outbound_message(msg)
        self.assertEqual(msg.from_email, 'HR Pro <hr@alrsheed.net>')
        self.assertEqual(msg.reply_to, ['hr@alrsheed.net'])


class EmailDeliveryStatusTests(SimpleTestCase):
    @override_settings(
        EMAIL_HOST='smtp.hostinger.com',
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST_USER='hr@alrsheed.net',
        DEFAULT_FROM_EMAIL='HR Pro <admin@alrsheed.net>',
    )
    def test_status_includes_effective_from_and_warning(self):
        status = email_delivery_status()
        self.assertTrue(status['smtp_ready'])
        self.assertEqual(status['effective_from'], 'HR Pro <hr@alrsheed.net>')
        self.assertIn('admin@alrsheed.net', from_email_smtp_mismatch_warning())
