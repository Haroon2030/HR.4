"""توافق المسير مع MySQL/MariaDB (Hostinger)."""
from apps.payroll.models import PayrollRun
from apps.payroll.services.engine import build_consolidated_payroll_run, lock_payroll_run
from apps.payroll.tests_financial_expert import TRANSFER, FinanceBase


class DatabaseCompatibilityTests(FinanceBase):
    """MySQL/MariaDB (Hostinger) لا تدعم SELECT ... FOR UPDATE OF."""

    def test_build_and_lock_without_select_for_update_of_support(self):
        from unittest import mock
        from django.db import connection
        from django.db.models.query import QuerySet

        self.emp(rate='0')
        calls = []
        real = QuerySet.select_for_update

        def spy(qs, *args, **kwargs):
            calls.append(kwargs.get('of'))
            if kwargs.get('of'):
                raise AssertionError('FOR UPDATE OF used on a backend that does not support it')
            return real(qs, *args, **kwargs)

        with mock.patch.object(type(connection.features), 'has_select_for_update_of', False), \
                mock.patch.object(QuerySet, 'select_for_update', spy):
            run = self.build(2026, 4)
            lock_payroll_run(run, self.user)
            cons = build_consolidated_payroll_run(
                [self.branch2], 2026, 4, self.user, salary_mode=TRANSFER, sponsorship_id=self.sp.id,
            )
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.LOCKED)
        self.assertTrue(calls)


# ══════════════════════════════════════════════════════════════════════════════
# 10) التصدير الشامل متعدد الأوراق
# ══════════════════════════════════════════════════════════════════════════════
