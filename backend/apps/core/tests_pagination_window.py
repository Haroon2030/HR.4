"""ترقيم الصفحات: نافذة أرقام قليلة تتحرك مع الصفحة الحالية."""
import re

from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.core.utils.pagination import page_window


class PageWindowTests(SimpleTestCase):
    def test_start_shows_first_pages(self):
        self.assertEqual(page_window(1, 49), [1, 2, 3, 4, 5])
        self.assertEqual(page_window(2, 49), [1, 2, 3, 4, 5])

    def test_window_moves_with_current_page(self):
        self.assertEqual(page_window(10, 49), [8, 9, 10, 11, 12])
        self.assertEqual(page_window(11, 49), [9, 10, 11, 12, 13])

    def test_end_shows_last_pages(self):
        self.assertEqual(page_window(49, 49), [45, 46, 47, 48, 49])
        self.assertEqual(page_window(1000, 1000), [996, 997, 998, 999, 1000])

    def test_fewer_pages_than_window(self):
        self.assertEqual(page_window(2, 3), [1, 2, 3])

    def test_out_of_range_and_invalid_input(self):
        self.assertEqual(page_window(99, 10), [6, 7, 8, 9, 10])
        self.assertEqual(page_window(0, 10), [1, 2, 3, 4, 5])
        self.assertEqual(page_window(None, 10), [])
        self.assertEqual(page_window(1, 0), [])


class PaginationComponentTests(SimpleTestCase):
    def _numbers(self, page_number, total_items=487, per_page=10):
        page_obj = Paginator(range(total_items), per_page).page(page_number)
        html = render_to_string(
            'components/hr_pagination.html',
            {'page_obj': page_obj, 'controls_only': True},
        )
        return [
            int(n) for n in re.findall(r'hr-pagination__num[^"]*"[^>]*>\s*(\d+)\s*<', html)
        ]

    def test_renders_only_window_not_all_pages(self):
        self.assertEqual(self._numbers(1), [1, 2, 3, 4, 5])

    def test_next_pages_appear_as_user_advances(self):
        self.assertEqual(self._numbers(10), [8, 9, 10, 11, 12])
        self.assertEqual(self._numbers(49), [45, 46, 47, 48, 49])
