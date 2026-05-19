"""اختبارات تخزين عدادات الشريط الجانبي مؤقتاً."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.core.services.sidebar_counts import (
    get_sidebar_counts,
    invalidate_sidebar_counts,
    sidebar_counts_cache_key,
)

User = get_user_model()


class SidebarCountsCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='cache_test', password='x')

    def test_counts_cached_after_compute(self):
        key = sidebar_counts_cache_key(self.user.pk)
        self.assertIsNone(cache.get(key))
        get_sidebar_counts(self.user)
        self.assertIsNotNone(cache.get(key))

    def test_invalidate_removes_cache(self):
        key = sidebar_counts_cache_key(self.user.pk)
        get_sidebar_counts(self.user)
        invalidate_sidebar_counts(self.user.pk)
        self.assertIsNone(cache.get(key))
