"""اختبارات مساعدات HTMX."""
from django.test import RequestFactory, TestCase

from apps.core.htmx_utils import wants_partial


class HtmxUtilsTests(TestCase):
    def test_wants_partial_by_header(self):
        request = RequestFactory().get('/employees/')
        request.META['HTTP_HX_TARGET'] = 'employees-list-panel'
        self.assertTrue(wants_partial(request, 'employees-list-panel'))
        self.assertFalse(wants_partial(request, 'other'))

    def test_wants_partial_by_query(self):
        request = RequestFactory().get('/employees/?partial=employees-list-panel')
        self.assertTrue(wants_partial(request, 'employees-list-panel'))
