"""اختبارات كتالوج التقارير للواجهة."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.web_views.reports import _grouped_reports_for_user

User = get_user_model()


class GroupedReportsForUserTests(TestCase):
    def test_grouped_reports_include_items_per_group(self):
        user = User.objects.create_user(username='report_viewer', password='x')
        grouped = _grouped_reports_for_user(user)
        self.assertTrue(len(grouped) > 0)
        for group in grouped:
            self.assertIn('items', group)
            self.assertTrue(len(group['items']) > 0)
            for item in group['items']:
                self.assertTrue(item.get('key'))
                self.assertTrue(item.get('title'))
