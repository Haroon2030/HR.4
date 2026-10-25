"""فلترة قائمة طلبات العمليات: نوع الطلب، الفرع، فترة التاريخ."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Branch, Company, PendingAction
from apps.core.services.pending_actions import create_pending_action
from apps.employees.models import Employee

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class PendingListFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='شركة')
        cls.branch_a = Branch.objects.create(name='فرع أ', code='F-A', company=company)
        cls.branch_b = Branch.objects.create(name='فرع ب', code='F-B', company=company)
        cls.admin = User.objects.create_user(
            username='ops_admin', password='x12345678', is_superuser=True, is_staff=True,
        )
        emp_a = Employee.objects.create(name='موظف أ', branch=cls.branch_a, basic_salary=Decimal('3000'))
        emp_b = Employee.objects.create(name='موظف ب', branch=cls.branch_b, basic_salary=Decimal('3000'))
        cls.leave = create_pending_action(
            action_type='leave', employee=emp_a, requested_by=cls.admin,
            payload={'leave_type': 'annual', 'date_from': '2026-06-01', 'date_to': '2026-06-05', 'days': 5},
        )
        cls.transfer = create_pending_action(
            action_type='transfer', employee=emp_b, requested_by=cls.admin,
            payload={'to_branch_id': cls.branch_a.id},
        )
        # طلب قديم لاختبار فلترة التاريخ
        PendingAction.objects.filter(pk=cls.transfer.pk).update(
            requested_at=timezone.now() - timedelta(days=40),
        )

    def _ids(self, **params):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('web:list_pending_actions'), {'tab': 'all', **params})
        self.assertEqual(r.status_code, 200)
        return {a.id for a in r.context['actions']}

    def test_no_filter_shows_both(self):
        self.assertTrue({self.leave.id, self.transfer.id} <= self._ids())

    def test_filter_by_type(self):
        ids = self._ids(type='leave')
        self.assertIn(self.leave.id, ids)
        self.assertNotIn(self.transfer.id, ids)

    def test_filter_hire_excludes_operations(self):
        ids = self._ids(type='hire')
        self.assertNotIn(self.leave.id, ids)
        self.assertNotIn(self.transfer.id, ids)

    def test_filter_by_branch(self):
        ids = self._ids(branch=str(self.branch_b.id))
        self.assertIn(self.transfer.id, ids)
        self.assertNotIn(self.leave.id, ids)

    def test_filter_by_date_range(self):
        since = (date.today() - timedelta(days=7)).isoformat()
        ids = self._ids(date_from=since)
        self.assertIn(self.leave.id, ids)
        self.assertNotIn(self.transfer.id, ids)
        ids = self._ids(date_to=since)
        self.assertIn(self.transfer.id, ids)
        self.assertNotIn(self.leave.id, ids)

    def test_invalid_values_are_ignored(self):
        self.assertTrue({self.leave.id, self.transfer.id} <= self._ids(type='bogus', branch='x', date_from='nope'))

    def test_pagination_keeps_filters(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('web:list_pending_actions'), {'tab': 'all', 'type': 'leave'})
        self.assertIn('type=leave', r.context['filter_qs'])
        self.assertIn('tab=all', r.context['filter_qs'])
