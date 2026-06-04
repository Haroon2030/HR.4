"""
قياس عدد استعلامات SQL ووقتها لصفحات الويب الرئيسية (تشخيص البطء).
الاستخدام: python manage.py profile_page_queries [--user admin]
"""
from __future__ import annotations

import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, reset_queries
from django.test import Client


PAGES = [
    ('لوحة التحكم', '/'),
    ('قائمة الموظفين', '/employees/'),
    ('تهيئة النظام', '/branches/'),
    ('طلبات العمليات', '/pending-actions/'),
    ('تقرير بصمة (شهر)', '/attendance/report/?from=2026-06-01&to=2026-06-30'),
    ('سجلات حضور', '/attendance/records/?from=2026-06-01&to=2026-06-30'),
    ('تقرير ملخص القوى', '/reports/headcount_summary/'),
    ('مسير رواتب', '/payroll/'),
    ('مستخدمون', '/users/'),
]


class Command(BaseCommand):
    help = 'Profile SQL query count and time for key web pages'

    def add_arguments(self, parser):
        parser.add_argument('--user', default='', help='Username (default: first superuser)')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stderr.write(
                self.style.WARNING('DEBUG=False — enabling query logging for this run only.'),
            )
        settings.DEBUG = True

        User = get_user_model()
        username = (options.get('user') or '').strip()
        if username:
            user = User.objects.filter(username=username).first()
        else:
            user = User.objects.filter(is_superuser=True).order_by('pk').first()
        if not user:
            self.stderr.write(self.style.ERROR('No user found.'))
            return

        client = Client()
        client.force_login(user)
        self.stdout.write(f'User: {user.username} (id={user.pk})\n')
        self.stdout.write(f'{"Page":<22} {"Status":<6} {"Queries":<8} {"SQL ms":<10} {"Total ms":<10}')
        self.stdout.write('-' * 60)

        totals = []
        for label, path in PAGES:
            reset_queries()
            t0 = time.perf_counter()
            try:
                resp = client.get(path, follow=True)
                status = resp.status_code
            except Exception as exc:
                status = f'ERR:{exc.__class__.__name__}'
                resp = None
            elapsed_ms = (time.perf_counter() - t0) * 1000
            nq = len(connection.queries)
            sql_ms = sum(float(q.get('time', 0)) for q in connection.queries) * 1000
            html_kb = len(resp.content) / 1024 if resp and hasattr(resp, 'content') else 0
            self.stdout.write(
                f'{label:<22} {str(status):<6} {nq:<8} {sql_ms:>8.1f}   {elapsed_ms:>8.1f}   ({html_kb:.0f} KB)',
            )
            totals.append((label, nq, sql_ms, elapsed_ms, html_kb))

        self.stdout.write('-' * 60)
        worst_q = max(totals, key=lambda x: x[1])
        worst_t = max(totals, key=lambda x: x[3])
        self.stdout.write(
            self.style.WARNING(
                f'Most queries: {worst_q[0]} ({worst_q[1]}). '
                f'Slowest total: {worst_t[0]} ({worst_t[3]:.0f} ms).',
            ),
        )
