"""
مصفوفة حالات التصفية مع المسير: يُصدَر (يُرحَّل) المسير فعلياً ثم يُصفّى الموظف بتواريخ مختلفة.

القاعدة: الشهر 30 يوماً دائماً، والراتب المصروف في مسير مُرحَّل لا يُصرف ثانيةً في التصفية،
وما صُرف زيادةً (توقف قبل نهاية الشهر) يُسترد، وما صُرف لأشهر بعد التوقف يُسترد كاملاً.
"""
from datetime import date
from decimal import Decimal

from apps.employees.models import EmployeeLoan
from apps.employees.services.settlement_financials import (
    compute_settlement_financials,
    net_settlement_total,
)
from apps.payroll.services.engine import lock_payroll_run

from .tests_financial_expert import FinanceBase

D = Decimal
# الراتب الإجمالي للموظف الافتراضي: 3000 + 1000 + 500 = 4500 ⇒ اليومي 150
GROSS = D('4500.00')
DAY = D('150.00')


class SettlementCasesTests(FinanceBase):
    def _settle(self, e, end):
        return compute_settlement_financials(e, end)

    def _issue(self, year, month):
        run = self.build(year, month)
        lock_payroll_run(run, self.user)
        return run

    # ── الشهر لم يُصرف بعد ────────────────────────────────────────────────
    def test_unpaid_month_stop_on_27_company_owes_27_days(self):
        e = self.emp(rate='0')
        fin = self._settle(e, date(2026, 4, 27))
        self.assertEqual(fin['prorated_salary'], DAY * 27)
        self.assertEqual(fin['overpaid_salary_recovery'], D('0.00'))
        self.assertEqual(fin['salary_already_paid'], D('0.00'))

    def test_unpaid_month_stop_on_last_day_of_30_day_month_owes_full(self):
        e = self.emp(rate='0')
        self.assertEqual(self._settle(e, date(2026, 4, 30))['prorated_salary'], GROSS)

    def test_unpaid_month_stop_on_31st_is_still_30_days(self):
        e = self.emp(rate='0')
        self.assertEqual(self._settle(e, date(2026, 5, 31))['prorated_salary'], GROSS)

    def test_unpaid_month_stop_on_30th_of_31_day_month_is_full_month(self):
        """30 مايو في شهر 31 يوماً: على قاعدة الـ30 يوماً هو الشهر كاملاً."""
        e = self.emp(rate='0')
        self.assertEqual(self._settle(e, date(2026, 5, 30))['prorated_salary'], GROSS)

    def test_february_last_day_is_full_month(self):
        e = self.emp(rate='0')
        self.assertEqual(self._settle(e, date(2026, 2, 28))['prorated_salary'], GROSS)

    def test_stop_on_first_day_owes_one_day(self):
        e = self.emp(rate='0')
        self.assertEqual(self._settle(e, date(2026, 4, 1))['prorated_salary'], DAY)

    # ── الشهر صُرف (مُرحَّل) ثم تصفية ────────────────────────────────────
    def test_paid_month_stop_on_27_employee_owes_3_days(self):
        e = self.emp(rate='0')
        self._issue(2026, 4)
        fin = self._settle(e, date(2026, 4, 27))
        self.assertEqual(fin['salary_already_paid'], GROSS)
        self.assertEqual(fin['prorated_salary'], D('0.00'))
        self.assertEqual(fin['overpaid_salary_recovery'], DAY * 3)
        self.assertEqual(fin['total_deductions'], DAY * 3)

    def test_paid_month_stop_on_last_day_nothing_due_nothing_recovered(self):
        e = self.emp(rate='0')
        self._issue(2026, 4)
        fin = self._settle(e, date(2026, 4, 30))
        self.assertEqual(fin['prorated_salary'], D('0.00'))
        self.assertEqual(fin['overpaid_salary_recovery'], D('0.00'))

    def test_paid_month_stop_on_first_day_recovers_29_days(self):
        e = self.emp(rate='0')
        self._issue(2026, 4)
        fin = self._settle(e, date(2026, 4, 1))
        self.assertEqual(fin['overpaid_salary_recovery'], DAY * 29)

    def test_paid_31_day_month_stop_on_29th_recovers_one_day(self):
        e = self.emp(rate='0')
        self._issue(2026, 5)
        fin = self._settle(e, date(2026, 5, 29))
        self.assertEqual(fin['overpaid_salary_recovery'], DAY)

    def test_paid_month_does_not_show_salary_again(self):
        """الراتب الصادر لا يظهر ثانيةً كمستحق جديد في التصفية."""
        e = self.emp(rate='0')
        self._issue(2026, 4)
        for day in (10, 20, 27, 30):
            self.assertEqual(self._settle(e, date(2026, 4, day))['prorated_salary'], D('0.00'))

    # ── أشهر لاحقة صُرفت بعد التوقف ───────────────────────────────────────
    def test_later_paid_months_are_recovered_in_full(self):
        e = self.emp(rate='0')
        self._issue(2026, 4)
        self._issue(2026, 5)
        fin = self._settle(e, date(2026, 4, 30))
        self.assertEqual(fin['overpaid_salary_recovery'], GROSS)  # شهر مايو بالكامل

    def test_earlier_paid_month_does_not_affect_current_month_settlement(self):
        e = self.emp(rate='0')
        self._issue(2026, 3)
        fin = self._settle(e, date(2026, 4, 27))
        self.assertEqual(fin['salary_already_paid'], D('0.00'))
        self.assertEqual(fin['prorated_salary'], DAY * 27)

    # ── مسودة غير مُرحَّلة لا تُحتسب مصروفة ──────────────────────────────
    def test_draft_run_is_not_counted_as_paid(self):
        e = self.emp(rate='0')
        self.build(2026, 4)  # بدون ترحيل
        fin = self._settle(e, date(2026, 4, 27))
        self.assertEqual(fin['salary_already_paid'], D('0.00'))
        self.assertEqual(fin['prorated_salary'], DAY * 27)

    # ── مباشرة داخل الشهر ─────────────────────────────────────────────────
    def test_hired_mid_month_and_stopped_same_month(self):
        e = self.emp(rate='0', hire=date(2026, 4, 11))
        fin = self._settle(e, date(2026, 4, 20))
        self.assertEqual(fin['prorated_salary'], DAY * 10)

    def test_hired_mid_month_paid_then_stopped_early_recovers_difference(self):
        e = self.emp(rate='0', hire=date(2026, 4, 11))
        self._issue(2026, 4)  # صُرف 20 يوماً (من 11 إلى 30)
        fin = self._settle(e, date(2026, 4, 20))
        self.assertEqual(fin['salary_already_paid'], DAY * 20)
        self.assertEqual(fin['overpaid_salary_recovery'], DAY * 10)

    # ── خصومات معلّقة مع الراتب المصروف ──────────────────────────────────
    def test_active_loan_balance_added_on_top_of_recovery(self):
        e = self.emp(rate='0')
        loan = EmployeeLoan.objects.create(
            employee=e, amount=D('1000'), monthly_deduction=D('250'), installments=4,
            issued_at=date(2026, 3, 1), first_deduction_date=date(2026, 5, 1),
        )
        loan.generate_installments()
        self._issue(2026, 4)
        fin = self._settle(e, date(2026, 4, 27))
        self.assertEqual(fin['loans_deduction'] + fin['overpaid_salary_recovery'],
                         fin['total_deductions'])
        self.assertGreater(fin['loans_deduction'], D('0'))

    # ── الصافي النهائي ────────────────────────────────────────────────────
    def test_net_unpaid_month_is_positive_salary_plus_entitlements(self):
        e = self.emp(rate='0')
        fin = self._settle(e, date(2026, 4, 27))
        net = net_settlement_total(eosb=D('1000'), leave_comp=D('200'), penalty=D('0'), financials=fin)
        self.assertEqual(net, D('1200') + DAY * 27)

    def test_net_paid_month_early_stop_subtracts_recovery(self):
        e = self.emp(rate='0')
        self._issue(2026, 4)
        fin = self._settle(e, date(2026, 4, 27))
        net = net_settlement_total(eosb=D('1000'), leave_comp=D('200'), penalty=D('0'), financials=fin)
        self.assertEqual(net, D('1200') - DAY * 3)

    def test_net_can_be_negative_when_recovery_exceeds_entitlements(self):
        e = self.emp(rate='0')
        self._issue(2026, 4)
        fin = self._settle(e, date(2026, 4, 1))
        net = net_settlement_total(eosb=D('0'), leave_comp=D('0'), penalty=D('0'), financials=fin)
        self.assertEqual(net, -DAY * 29)

    # ── مسير موحّد (كل الفروع) ────────────────────────────────────────────
    def test_consolidated_locked_run_counts_as_paid(self):
        from apps.employees.services.employee_view_data import _paid_salary_by_month
        from apps.payroll.services.engine import build_consolidated_payroll_run
        e = self.emp(rate='0')
        cons = build_consolidated_payroll_run(
            [self.branch], 2026, 4, self.user, salary_mode='transfer', sponsorship_id=self.sp.id,
        )
        lock_payroll_run(cons, self.user)
        fin = self._settle(e, date(2026, 4, 27))
        self.assertEqual(fin['salary_already_paid'], GROSS)
        self.assertEqual(fin['overpaid_salary_recovery'], DAY * 3)
        self.assertEqual(_paid_salary_by_month(e), {'2026-04': float(GROSS)})
