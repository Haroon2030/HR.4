"""تقارير الحضور الجديدة، اختيار الأعمدة، وPDF الرسمي."""
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from apps.attendance.models import AttendancePunch, BiometricDevice
from apps.core.web_views.reports import _apply_columns, _selected_column_indexes

User = get_user_model()


class _Req:
    def __init__(self, getlist):
        self.GET = type('G', (), {'getlist': staticmethod(lambda k: getlist if k == 'cols' else [])})()


class ColumnSelectionTests(TestCase):
    def test_indexes_none_when_all_or_empty(self):
        self.assertIsNone(_selected_column_indexes(_Req([]), 3))
        self.assertIsNone(_selected_column_indexes(_Req(['0', '1', '2']), 3))

    def test_indexes_ignore_invalid_and_out_of_range(self):
        self.assertEqual(_selected_column_indexes(_Req(['2', 'x', '9', '0']), 4), [0, 2])

    def test_apply_columns_filters_header_and_rows(self):
        data = {'columns': ['أ', 'ب', 'ج'], 'rows': [[1, 2, 3], [4, 5, 6]], 'note': 'n'}
        out = _apply_columns(data, [0, 2])
        self.assertEqual(out['columns'], ['أ', 'ج'])
        self.assertEqual(out['rows'], [[1, 3], [4, 6]])
        self.assertEqual(out['note'], 'n')
        self.assertIs(_apply_columns(data, None), data)


class AttendanceReportsTests(TestCase):
    def setUp(self):
        cache.clear()  # كاش التقارير يُشارَك بين الاختبارات بنفس معرّف المستخدم
        self.admin = User.objects.create_superuser('rep_admin', 'r@example.com', 'x-pass-123')
        self.client = Client()
        self.client.force_login(self.admin)
        self.device = BiometricDevice.objects.create(name='جهاز التقارير', ip_address='192.168.1.60', port=4370)
        self.day = timezone.localdate()

    def _punch(self, user_id, hour):
        naive = datetime(self.day.year, self.day.month, self.day.day, hour, 0)
        AttendancePunch.objects.create(
            device=self.device, device_user_id=user_id, device_user_name=f'مستخدم {user_id}',
            punched_at=timezone.make_aware(naive), punch_type=AttendancePunch.PunchType.CHECK_IN,
        )

    def _report(self, key, **params):
        qs = '&'.join(f'{k}={v}' for k, v in params.items())
        return self.client.get(f'/reports/{key}/' + (f'?{qs}' if qs else ''))

    def test_catalog_lists_new_attendance_reports(self):
        keys = {r['key'] for r in self._report('attendance_devices_status').context['reports']}
        self.assertTrue({'attendance_monthly', 'attendance_incomplete', 'attendance_devices_status'} <= keys)

    def test_devices_status_report_lists_device(self):
        response = self._report('attendance_devices_status')
        self.assertEqual(response.status_code, 200)
        names = [row[0] for row in response.context['data']['rows']]
        self.assertIn('جهاز التقارير', names)

    def test_incomplete_report_flags_unmapped_single_punch(self):
        self._punch(5, 8)
        response = self._report('attendance_incomplete', **{'from': self.day, 'to': self.day})
        self.assertEqual(response.status_code, 200)
        rows = response.context['data']['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][-1], 'غير مربوط بموظف')

    def test_monthly_report_skips_unmapped_with_note(self):
        self._punch(6, 8)
        response = self._report('attendance_monthly', **{'from': self.day, 'to': self.day})
        self.assertEqual(response.status_code, 200)
        data = response.context['data']
        self.assertEqual(data['rows'], [])
        self.assertIn('غير مربوط', data['note'])

    def test_column_selection_in_detail(self):
        response = self._report('attendance_devices_status', cols=0, **{'from': self.day, 'to': self.day})
        data = response.context['data']
        self.assertEqual(data['columns'], ['الجهاز'])
        self.assertEqual(len(response.context['column_choices']), 6)

    def test_pdf_export_is_official_pdf(self):
        response = self.client.get('/reports/attendance_devices_status/export-pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        wide = self.client.get('/reports/attendance_devices_status/export-pdf/?cols=0&cols=3')
        self.assertTrue(wide.content.startswith(b'%PDF'))

    def test_pdf_requires_export_permission(self):
        plain = User.objects.create_user('rep_plain', 'p@example.com', 'x-pass-123')
        client = Client()
        client.force_login(plain)
        self.assertNotEqual(client.get('/reports/attendance_devices_status/export-pdf/').status_code, 200)


class AllReportsExportTests(TestCase):
    """كل تقرير في الفهرس يجب أن يعرض ويُصدَّر Excel وPDF دون خطأ (يشمل عناوين فيها / مثل «الغياب / الإجازات»)."""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('all_rep_admin', 'all@example.com', 'x-pass-123')
        self.client = Client()
        self.client.force_login(self.admin)

    def test_every_catalog_report_renders_and_exports(self):
        from apps.core.web_views.reports import REPORTS

        failures = []
        for report in REPORTS:
            key = report['key']
            for suffix in ('', 'export/', 'export-pdf/'):
                status = self.client.get(f'/reports/{key}/{suffix}').status_code
                if status != 200:
                    failures.append(f'{key}/{suffix} -> {status}')
        self.assertEqual(failures, [])


class InsightsTests(TestCase):
    def test_analyze_table_picks_category_and_skips_phone_numbers(self):
        from apps.core.services.report_insights import analyze_table

        columns = ['الاسم', 'الفرع', 'الجوال', 'الراتب']
        rows = [
            [f'موظف {i}', 'الرياض' if i < 7 else 'جدة', f'05{10000000 + i}', 1000 + i * 10]
            for i in range(10)
        ]
        result = analyze_table(columns, rows)
        texts = ' '.join(i['text'] for i in result['insights'])
        self.assertIn('الفرع', texts)
        self.assertIn('الراتب', texts)
        self.assertNotIn('الجوال', texts)
        self.assertEqual(result['chart']['items'][0]['label'], 'الرياض')
        self.assertEqual(result['chart']['items'][0]['pct'], 70)

    def test_analyze_empty_table_gives_guidance(self):
        from apps.core.services.report_insights import analyze_table

        result = analyze_table(['أ'], [])
        self.assertEqual(result['insights'][0]['tone'], 'info')
        self.assertIsNone(result['chart'])


class ReportsCenterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('center_admin', 'c@example.com', 'x-pass-123')
        self.client = Client()
        self.client.force_login(self.admin)

    def test_index_renders_management_reading_and_catalog(self):
        response = self.client.get('/reports/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'القراءة الإدارية')
        self.assertContains(response, 'كتالوج التقارير')
        overview = response.context['overview']
        self.assertEqual(len(overview['kpis']), 6)
        self.assertEqual(len(overview['series']), 6)
        self.assertTrue(overview['insights'])

    def test_detail_shows_reading_panel(self):
        response = self.client.get('/reports/attendance_devices_status/')
        self.assertContains(response, 'القراءة الإدارية')
        self.assertIn('analysis', response.context)


class PeriodReportsFlagTests(TestCase):
    """أزرار الفترات والتواريخ تظهر فقط للتقارير التي تتأثر بالفترة فعلاً."""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('period_admin', 'pe@example.com', 'x-pass-123')
        self.client = Client()
        self.client.force_login(self.admin)

    def test_flag_matches_builder_source(self):
        """أي منشئ تقرير يستخدم تواريخ الفلتر يجب أن يكون ضمن PERIOD_REPORT_KEYS (والعكس)."""
        import inspect
        import re

        from apps.core.web_views.reports import BUILDERS, PERIOD_REPORT_KEYS

        pattern = re.compile(r"_parse_filter_dates\(|date_from|date_to|_attendance_daily_rows\(|filters\['date")
        mismatches = [
            key for key, builder in BUILDERS.items()
            if bool(pattern.search(inspect.getsource(builder))) != (key in PERIOD_REPORT_KEYS)
        ]
        self.assertEqual(mismatches, [])
        self.assertLessEqual(PERIOD_REPORT_KEYS, set(BUILDERS))

    def test_snapshot_report_hides_presets_and_dates(self):
        response = self.client.get('/reports/housing/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_period_report'])
        self.assertEqual(response.context['period_presets'], [])
        self.assertContains(response, 'يعرض الوضع الحالي ولا يتأثر بالفترة')
        # لا حقول فترة في فلتر التقرير (حقل from المخفي لاختيار الأعمدة مقصود، وحاسبة التواريخ العامة خارج الفلتر)
        self.assertNotContains(response, 'aria-label="من تاريخ"')
        self.assertNotContains(response, 'aria-label="إلى تاريخ"')

    def test_period_report_shows_presets_and_dates(self):
        response = self.client.get('/reports/leaves/')
        self.assertTrue(response.context['is_period_report'])
        self.assertEqual(len(response.context['period_presets']), 4)
        self.assertNotContains(response, 'يعرض الوضع الحالي ولا يتأثر بالفترة')
        self.assertContains(response, 'aria-label="من تاريخ"')
        self.assertContains(response, 'aria-label="إلى تاريخ"')

    def test_pdf_period_text_for_snapshot(self):
        response = self.client.get('/reports/housing/export-pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF'))
