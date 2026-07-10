"""اختبارات لوحة تحكم الصيانة."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Branch, Company, Role, UserProfile
from apps.core.web_views._helpers import _is_general_manager
from apps.maintenance.models import MaintenanceRequest, MaintenanceTrade
from apps.maintenance.selectors.dashboard import build_maintenance_dashboard
from apps.maintenance.services.requests import create_maintenance_request

User = get_user_model()


class MaintenanceDashboardSelectorTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='شركة اختبار', commercial_record='2020202020')
        self.branch_a = Branch.objects.create(code='DA', name='فرع أ', company=self.company)
        self.branch_b = Branch.objects.create(code='DB', name='فرع ب', company=self.company)
        self.user = User.objects.create_user(username='bm_dash', password='pass')
        MaintenanceTrade.objects.create(code='PLUM', name='سباك')

    def test_build_maintenance_dashboard_kpis(self):
        create_maintenance_request(
            branch=self.branch_a,
            title='تكييف',
            description='معطل',
            requested_by=self.user,
            priority=MaintenanceRequest.Priority.URGENT,
        )
        create_maintenance_request(
            branch=self.branch_b,
            title='إضاءة',
            description='طفاة',
            requested_by=self.user,
        )
        req_done = create_maintenance_request(
            branch=self.branch_a,
            title='مصعد',
            description='تم',
            requested_by=self.user,
        )
        MaintenanceRequest.objects.filter(pk=req_done.pk).update(
            status=MaintenanceRequest.Status.BRANCH_CONFIRMED,
            branch_confirmed_at=timezone.now(),
        )

        data = build_maintenance_dashboard()
        kpis = data['kpis']

        self.assertEqual(kpis['open_total'], 2)
        self.assertEqual(kpis['pending'], 2)
        self.assertEqual(kpis['urgent_open'], 1)
        self.assertEqual(kpis['completed_month'], 1)
        self.assertEqual(data['total_requests'], 3)
        self.assertEqual(len(data['weekly_trend']), 7)
        self.assertTrue(any(row['branch__name'] for row in data['top_branches']))


class DashboardMaintenanceSectionViewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='شركة GM', commercial_record='3030303030')
        self.branch = Branch.objects.create(code='GM1', name='الفرع الرئيسي', company=self.company)

        self.gm = User.objects.create_user(username='gm_user', password='pass')
        gm_role, _ = Role.objects.get_or_create(
            role_type=Role.RoleType.HR_MANAGER,
            defaults={'name': 'مدير موارد', 'is_system_role': True},
        )
        UserProfile.objects.update_or_create(
            user=self.gm,
            defaults={'role': gm_role},
        )
        self.gm = User.objects.select_related('profile__role').get(pk=self.gm.pk)

        self.regular = User.objects.create_user(username='emp_user', password='pass')
        emp_role, _ = Role.objects.get_or_create(
            role_type=Role.RoleType.EMPLOYEE,
            defaults={'name': 'موظف', 'is_system_role': True},
        )
        UserProfile.objects.update_or_create(
            user=self.regular,
            defaults={'role': emp_role, 'branch': self.branch},
        )

        create_maintenance_request(
            branch=self.branch,
            title='طلب اختبار',
            description='وصف',
            requested_by=self.gm,
        )

    def test_gm_sees_maintenance_section(self):
        self.assertTrue(_is_general_manager(self.gm))
        self.client.force_login(self.gm)
        response = self.client.get(reverse('web:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'الصيانة')
        self.assertContains(response, 'مفتوحة')
        self.assertNotContains(response, 'آخر الطلبات')
        self.assertNotContains(response, 'تنبيهات عاجلة')
        self.assertContains(response, 'الموارد البشرية')
        self.assertNotContains(response, 'آخر طلبات التوظيف')
        self.assertNotContains(response, 'تنبيهات معلّقة')
        self.assertContains(response, 'hr-dashboard-section__body')

    def test_regular_user_sees_inbox_not_overview(self):
        self.client.force_login(self.regular)
        response = self.client.get(reverse('web:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'صندوق المهام')
        self.assertNotContains(response, 'hr-dashboard-section')
        self.assertNotContains(response, 'توزيع حالات الصيانة')
