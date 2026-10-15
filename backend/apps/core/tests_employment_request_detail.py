"""طلبات التوظيف: الصفحة الفردية، ومصدر رؤية واحد للقائمة والوارد."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Branch, Company, Permission, Role, UserProfile
from apps.core.web_views.pending_actions import _user_visible_hire_requests
from apps.employees.models import EmploymentRequest

User = get_user_model()


class EmploymentRequestDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Co-ER', tax_number='1', commercial_record='1')
        cls.branch = Branch.objects.create(name='فرع ER', code='ER-1', company=company)
        cls.manager = User.objects.create_user(username='er_branch_mgr', password='Pass-User-99!')
        cls.branch.manager = cls.manager
        cls.branch.save(update_fields=['manager'])

        role = Role.objects.create(name='مدير فرع ER', role_type=Role.RoleType.MANAGER)
        perms = Permission.objects.filter(code__in=['operations.view', 'operations.approve_branch'])
        role.permissions.set(perms)
        UserProfile.objects.filter(user=cls.manager).update(role=role, branch=cls.branch)

        cls.requester = User.objects.create_user(username='er_req', password='Pass-User-99!')
        cls.branch_stage = EmploymentRequest.objects.create(
            name='طلب مرحلة الفرع', branch=cls.branch, requested_by=cls.requester,
            status=EmploymentRequest.Status.PENDING_BRANCH,
        )
        cls.officer_stage = EmploymentRequest.objects.create(
            name='طلب مرحلة الأخصائي', branch=cls.branch, requested_by=cls.requester,
            status=EmploymentRequest.Status.PENDING_OFFICER,
        )

    def setUp(self):
        self.client.force_login(User.objects.get(pk=self.manager.pk))

    def test_branch_manager_opens_request_waiting_for_branch_approval(self):
        resp = self.client.get(reverse('web:employment_request_detail', args=[self.branch_stage.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'طلب مرحلة الفرع')

    def test_branch_manager_cannot_open_request_past_branch_stage(self):
        resp = self.client.get(reverse('web:employment_request_detail', args=[self.officer_stage.id]), follow=True)
        self.assertRedirects(resp, reverse('web:list_employment_requests'))
        self.assertContains(resp, 'ليس ضمن ما تستطيع الاطلاع عليه')

    def test_operations_inbox_and_detail_use_the_same_rule(self):
        ids = set(_user_visible_hire_requests(User.objects.get(pk=self.manager.pk))
                  .values_list('id', flat=True))
        self.assertIn(self.branch_stage.id, ids)
        self.assertNotIn(self.officer_stage.id, ids)

    def test_eye_button_in_operations_list_points_to_the_request(self):
        resp = self.client.get(reverse('web:list_pending_actions'), {'tab': 'inbox'})
        self.assertContains(resp, reverse('web:employment_request_detail', args=[self.branch_stage.id]))
