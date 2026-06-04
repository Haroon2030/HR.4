"""اختبارات كاش لوحة التحكم."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.core.models import Branch, Company
from apps.core.services.dashboard_cache import (
    dashboard_overview_cache_key,
    get_dashboard_overview,
    invalidate_dashboard_overview,
)

User = get_user_model()


class DashboardCacheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Co', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='Main', code='M1', company=cls.company)
        cls.user = User.objects.create_user(username='dash_cache', password='x')

    def setUp(self):
        cache.clear()

    def test_overview_cached_then_invalidated(self):
        overview1, cached1 = get_dashboard_overview(self.user, [self.branch.pk])
        self.assertFalse(cached1)
        overview2, cached2 = get_dashboard_overview(self.user, [self.branch.pk])
        self.assertTrue(cached2)
        self.assertEqual(overview1['stats'], overview2['stats'])

        invalidate_dashboard_overview(self.user.pk)
        _, cached3 = get_dashboard_overview(self.user, [self.branch.pk])
        self.assertFalse(cached3)

    def test_cache_key_changes_with_version(self):
        key1 = dashboard_overview_cache_key(self.user.pk, [self.branch.pk])
        invalidate_dashboard_overview(self.user.pk)
        key2 = dashboard_overview_cache_key(self.user.pk, [self.branch.pk])
        self.assertNotEqual(key1, key2)
