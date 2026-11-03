"""إعادة محاولة الاتصال عند MySQL 1040 وتحويله إلى 503 في الـ API."""
from django.test import SimpleTestCase


class TooManyConnectionsRetryTests(SimpleTestCase):
    class _Err(Exception):
        pass

    def test_retries_then_succeeds_on_1040(self):
        from config.db_backends.retry import connect_with_retry

        calls, slept = [], []

        def connect():
            calls.append(1)
            if len(calls) < 3:
                raise self._Err(1040, 'Too many connections')
            return 'conn'

        self.assertEqual(connect_with_retry(connect, self._Err, sleep=slept.append), 'conn')
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(slept), 2)

    def test_gives_up_after_all_retries(self):
        from config.db_backends.retry import CONNECT_RETRY_DELAYS, connect_with_retry

        slept = []

        def connect():
            raise self._Err(1040, 'Too many connections')

        with self.assertRaises(self._Err):
            connect_with_retry(connect, self._Err, sleep=slept.append)
        self.assertEqual(len(slept), len(CONNECT_RETRY_DELAYS))

    def test_other_errors_not_retried(self):
        from config.db_backends.retry import connect_with_retry

        slept = []

        def connect():
            raise self._Err(1045, 'Access denied')

        with self.assertRaises(self._Err):
            connect_with_retry(connect, self._Err, sleep=slept.append)
        self.assertEqual(slept, [])

    def test_api_handler_returns_503_for_1040(self):
        from django.db.utils import OperationalError

        from apps.core.exceptions import custom_api_exception_handler

        response = custom_api_exception_handler(OperationalError(1040, 'Too many connections'), {'request': None})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Retry-After'], '30')
