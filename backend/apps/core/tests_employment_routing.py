"""قاعدة فرع/إدارة في طلب التوظيف، وتجاوز المرحلة الأولى عند غياب جهة الموافقة."""
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.core.models import Branch, Company
from apps.core.services import employment_requests as svc
from apps.employees.forms import EmploymentRequestForm
from apps.employees.models import EmploymentRequest
from apps.setup.models import Administration

User = get_user_model()


def _form(**extra):
    data = {'name': 'مرشح', 'basic_salary': '3000', **extra}
    pdf = SimpleUploadedFile('c.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')
    return EmploymentRequestForm(data, {'commencement_document': pdf})


class BranchOrAdministrationRuleTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة')
        self.branch = Branch.objects.create(name='فرع', code='RB1', company=company)
        self.administration = Administration.objects.create(code='RA1', name='إدارة')

    def test_neither_is_rejected(self):
        form = _form()
        self.assertFalse(form.is_valid())
        self.assertIn('branch', form.errors)

    def test_branch_only_is_valid(self):
        self.assertTrue(_form(branch=self.branch.pk).is_valid())

    def test_administration_only_is_valid(self):
        self.assertTrue(_form(administration=self.administration.pk).is_valid())

    def test_both_is_valid(self):
        self.assertTrue(_form(branch=self.branch.pk, administration=self.administration.pk).is_valid())


class HireRowActionLinkTests(TestCase):
    def test_approve_link_opens_request_page_on_decision_card(self):
        from django.urls import reverse
        from apps.core.web_views.pending_actions import _wrap_hire

        admin = User.objects.create_user('hireadmin', password='x', is_superuser=True)
        req = EmploymentRequest.objects.create(
            name='مرشح', status=EmploymentRequest.Status.PENDING_GM,
        )
        row = _wrap_hire(req, admin)
        self.assertEqual(
            row.act_url, reverse('web:employment_request_detail', args=[req.id]) + '#decision-card',
        )
        self.assertTrue(row.can_act)  # السوبر أدمن يستطيع التصرف في مرحلة مدير الموارد


class UnifiedHireFlowTests(TestCase):
    """طلبات التوظيف تُدار من القائمة الموحّدة وصفحة الطلب، والقائمة القديمة تحوّل إليها."""

    def setUp(self):
        from django.test import Client
        self.admin = User.objects.create_user('uadmin', password='x', is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin)

    def _req(self, status):
        return EmploymentRequest.objects.create(name=f'مرشح {status}', status=status)

    def test_legacy_list_redirects_to_unified_list(self):
        from django.urls import reverse
        base = reverse('web:list_pending_actions')
        cases = {
            '': 'review', '?status=pending_gm': 'pending_gm', '?status=approved': 'approved',
            '?status=rejected': 'rejected', '?status=unknown': 'review',
        }
        for query, tab in cases.items():
            resp = self.client.get(reverse('web:list_employment_requests') + query)
            self.assertRedirects(resp, f'{base}?tab={tab}&type=hire')

    def test_decision_card_shows_forms_for_each_stage(self):
        from django.urls import reverse
        expectations = {
            EmploymentRequest.Status.PENDING_BRANCH: 'approve_employment_request',
            EmploymentRequest.Status.PENDING_GM: 'gm_approve_employment_request',
            EmploymentRequest.Status.PENDING_OFFICER: 'officer_approve_employment_request',
        }
        for status, url_name in expectations.items():
            req = self._req(status)
            page = self.client.get(reverse('web:employment_request_detail', args=[req.id]))
            self.assertContains(page, 'id="decision-card"')
            self.assertContains(page, reverse(f'web:{url_name}', args=[req.id]))
            self.assertContains(page, reverse('web:reject_employment_request', args=[req.id]))

    def test_rejected_tab_lists_rejected_hires(self):
        from django.urls import reverse
        self._req(EmploymentRequest.Status.REJECTED)
        page = self.client.get(reverse('web:list_pending_actions') + '?tab=rejected')
        self.assertEqual(page.context['counts']['rejected'], 1)
        self.assertContains(page, 'مرشح rejected')


class SkipFirstStageTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة')
        self.branch = Branch.objects.create(name='فرع', code='RB2', company=company)
        self.administration = Administration.objects.create(code='RA2', name='إدارة بلا مدير')

    def _request(self, **kwargs):
        return EmploymentRequest.objects.create(
            name='مرشح', status=EmploymentRequest.Status.PENDING_BRANCH, **kwargs,
        )

    def test_administration_without_manager_skips_to_gm(self):
        req = self._request(administration=self.administration)
        self.assertTrue(svc.skip_first_stage_if_unrouted(req))
        req.refresh_from_db()
        self.assertEqual(req.status, EmploymentRequest.Status.PENDING_GM)
        self.assertIn('تجاوز', req.branch_notes)

    def test_branch_without_manager_skips_to_gm(self):
        req = self._request(branch=self.branch)
        self.assertTrue(svc.skip_first_stage_if_unrouted(req))

    def test_branch_with_manager_is_not_skipped(self):
        self.branch.manager = User.objects.create_user('bm', password='x')
        self.branch.save(update_fields=['manager'])
        req = self._request(branch=self.branch)
        self.assertFalse(svc.skip_first_stage_if_unrouted(req))
        req.refresh_from_db()
        self.assertEqual(req.status, EmploymentRequest.Status.PENDING_BRANCH)

    def test_administration_with_manager_is_not_skipped(self):
        self.administration.manager = User.objects.create_user('am', password='x')
        self.administration.save(update_fields=['manager'])
        req = self._request(administration=self.administration)
        self.assertFalse(svc.skip_first_stage_if_unrouted(req))

    def test_only_pending_first_stage_requests_are_touched(self):
        req = self._request(administration=self.administration)
        req.status = EmploymentRequest.Status.PENDING_OFFICER
        req.save(update_fields=['status'])
        self.assertFalse(svc.skip_first_stage_if_unrouted(req))
