"""اختبارات المرحلة 2/3 — ترقيم مفتاحي، بحث موظفين، إحصائيات البصمة."""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.attendance.models import AttendancePunch, BiometricDevice
from apps.attendance.selectors.punch_records import get_punch_stats
from apps.core.models import Branch, Company
from apps.core.selectors.employee_search import apply_employee_search
from apps.core.utils.pagination import decode_keyset_cursor, encode_keyset_cursor, keyset_paginate_queryset
from apps.employees.models import Employee


class KeysetPaginationTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة اختبار', tax_number='1', commercial_record='1')
        self.branch = Branch.objects.create(name='فرع اختبار', code='T1', company=company)
        self.device = BiometricDevice.objects.create(
            name='جهاز 1',
            ip_address='192.168.1.10',
            branch=self.branch,
        )
        base = timezone.now()
        for i in range(5):
            AttendancePunch.objects.create(
                device=self.device,
                device_user_id=100 + i,
                punched_at=base - timedelta(minutes=i),
                punch_type=AttendancePunch.PunchType.CHECK_IN,
            )

    def test_encode_decode_cursor_roundtrip(self):
        dt = timezone.now()
        raw = encode_keyset_cursor(dt, 42)
        decoded = decode_keyset_cursor(raw)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded[1], 42)

    def test_keyset_first_and_next_page(self):
        qs = AttendancePunch.objects.filter(device=self.device)
        page1 = keyset_paginate_queryset(qs, per_page=2)
        self.assertEqual(len(page1), 2)
        self.assertTrue(page1.has_next)
        self.assertFalse(page1.has_previous)

        page2 = keyset_paginate_queryset(
            qs, per_page=2, after=page1.cursor_after,
        )
        self.assertEqual(len(page2), 2)
        self.assertTrue(page2.has_previous)


class EmployeeSearchSelectorTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة', tax_number='2', commercial_record='2')
        self.branch = Branch.objects.create(name='الرياض', code='RYD', company=company)
        Employee.objects.create(
            name='أحمد محمد',
            employee_number='E100',
            id_number='1234567890',
            branch=self.branch,
        )
        Employee.objects.create(
            name='سارة علي',
            employee_number='E200',
            branch=self.branch,
        )

    def test_search_by_employee_number(self):
        qs = Employee.objects.all()
        filtered = apply_employee_search(qs, 'E100')
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first().name, 'أحمد محمد')

    def test_search_by_branch_name_subquery(self):
        qs = Employee.objects.all()
        filtered = apply_employee_search(qs, 'الرياض')
        self.assertEqual(filtered.count(), 2)


class PunchStatsAggregateTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة', tax_number='3', commercial_record='3')
        self.branch = Branch.objects.create(name='فرع', code='B1', company=company)
        self.device = BiometricDevice.objects.create(
            name='D1',
            ip_address='10.0.0.1',
            branch=self.branch,
        )
        t0 = timezone.now()
        AttendancePunch.objects.create(
            device=self.device,
            device_user_id=1,
            punched_at=t0 - timedelta(hours=2),
            punch_type=AttendancePunch.PunchType.CHECK_IN,
        )
        AttendancePunch.objects.create(
            device=self.device,
            device_user_id=1,
            punched_at=t0,
            punch_type=AttendancePunch.PunchType.CHECK_OUT,
        )

    def test_stats_use_min_max_bounds(self):
        qs = AttendancePunch.objects.filter(device=self.device)
        stats = get_punch_stats(qs)
        self.assertEqual(stats['total'], 2)
        self.assertIsNotNone(stats['first_punch'])
        self.assertIsNotNone(stats['last_punch'])
        self.assertLess(stats['first_punch'], stats['last_punch'])
