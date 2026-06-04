"""اختبارات كاش جداول الإعداد."""
from django.core.cache import cache
from django.test import TestCase

from apps.core.services.setup_cache import get_cached_list, invalidate_setup_cache


class SetupCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_list_cached_and_invalidated(self):
        calls = {'n': 0}

        def builder():
            calls['n'] += 1
            return [1, 2, 3]

        first = get_cached_list('test_list', builder)
        second = get_cached_list('test_list', builder)
        self.assertEqual(first, [1, 2, 3])
        self.assertEqual(second, [1, 2, 3])
        self.assertEqual(calls['n'], 1)

        invalidate_setup_cache('test_list')
        third = get_cached_list('test_list', builder)
        self.assertEqual(third, [1, 2, 3])
        self.assertEqual(calls['n'], 2)
