"""رفض/إرجاع طلب التوظيف بسبب إلزامي يصل لمقدّم الطلب، ثم تعديله وإعادة إرساله."""
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.core.models import AppModule, Branch, Company, Notification, Permission, Role
from apps.core.services import employment_requests as svc
from apps.employees.models import EmploymentRequest

User = get_user_model()
PDF = b'%PDF-1.4\n%%EOF'


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class EmploymentReturnTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('retadmin', password='x', is_superuser=True, is_staff=True)
        self.requester = User.objects.create_user('retrequester', password='x')
        company = Company.objects.create(name='شركة الإرجاع')
        self.branch = Branch.objects.create(name='فرع الإرجاع', code='RT1', company=company)
        self._make_requester_realistic()
        self.req = EmploymentRequest.objects.create(
            name='مرشح للإرجاع', branch=self.branch, requested_by=self.requester,
            status=EmploymentRequest.Status.PENDING_GM, basic_salary=3000,
            commencement_document=SimpleUploadedFile('c.pdf', PDF, content_type='application/pdf'),
        )
        self.admin_client = Client()
        self.admin_client.force_login(self.admin)
        self.requester_client = Client()
        self.requester_client.force_login(self.requester)

    def _make_requester_realistic(self):
        """مقدّم الطلب أخصائي إدخال بيانات: يرى العمليات ويتبع فرعه (ليس مدير نظام)."""
        module, _ = AppModule.objects.get_or_create(
            code='operations', defaults={'name': 'operations', 'icon': 'circle', 'order': 50},
        )
        perm, _ = Permission.objects.get_or_create(
            code='operations.view',
            defaults={'module': module, 'operation': Permission.Operation.VIEW, 'name': 'operations.view'},
        )
        role = Role.objects.create(name='مقدّم طلبات', role_type=Role.RoleType.SPECIALIST)
        role.permissions.add(perm)
        profile = self.requester.profile
        profile.role = role
        profile.branch = self.branch
        profile.save(update_fields=['role', 'branch'])

    def _url(self, name):
        return reverse(f'web:{name}', args=[self.req.id])

    # ── الإرجاع ──────────────────────────────────────────────────────────
    def test_return_requires_a_reason(self):
        self.admin_client.post(self._url('return_employment_request'), {'review_notes': '   '})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, EmploymentRequest.Status.PENDING_GM)

    def test_return_stores_reason_and_notifies_requester(self):
        self.admin_client.post(self._url('return_employment_request'), {'review_notes': 'الراتب غير مطابق للعقد'})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, EmploymentRequest.Status.RETURNED)
        self.assertEqual(self.req.return_notes, 'الراتب غير مطابق للعقد')
        self.assertEqual(self.req.returned_by, self.admin)
        self.assertTrue(self.req.returned_at)
        note = Notification.objects.filter(recipient=self.requester).first()
        self.assertIsNotNone(note)
        self.assertIn('الراتب غير مطابق للعقد', note.message)

    def test_final_reject_also_requires_a_reason(self):
        self.admin_client.post(self._url('reject_employment_request'), {'review_notes': ''})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, EmploymentRequest.Status.PENDING_GM)
        self.admin_client.post(self._url('reject_employment_request'), {'review_notes': 'مرفوض لعدم الحاجة'})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, EmploymentRequest.Status.REJECTED)
        self.assertEqual(self.req.review_notes, 'مرفوض لعدم الحاجة')

    def test_cannot_return_a_closed_request(self):
        EmploymentRequest.objects.filter(pk=self.req.pk).update(status=EmploymentRequest.Status.APPROVED)
        self.req.refresh_from_db()
        with self.assertRaises(ValueError):
            svc.return_for_edit(self.req, self.admin, 'سبب')

    # ── التعديل وإعادة الإرسال ───────────────────────────────────────────
    def _returned(self):
        svc.return_for_edit(self.req, self.admin, 'عدّل الراتب')
        self.req.refresh_from_db()

    def test_requester_sees_reason_and_prefilled_edit_form(self):
        self._returned()
        detail = self.requester_client.get(self._url('employment_request_detail'))
        self.assertContains(detail, 'عدّل الراتب')
        self.assertContains(detail, self._url('edit_returned_employment_request'))
        self.assertContains(detail, self._url('resubmit_employment_request'))
        form = self.requester_client.get(self._url('edit_returned_employment_request'))
        self.assertContains(form, 'value="مرشح للإرجاع"')
        self.assertContains(form, 'عدّل الراتب')

    def test_requester_edits_then_resubmits(self):
        self._returned()
        self.requester_client.post(self._url('edit_returned_employment_request'), {
            'name': 'مرشح مُعدَّل', 'basic_salary': '3500', 'branch': self.branch.pk,
        })
        self.req.refresh_from_db()
        self.assertEqual(self.req.name, 'مرشح مُعدَّل')
        self.assertEqual(int(self.req.basic_salary), 3500)
        self.assertEqual(self.req.status, EmploymentRequest.Status.RETURNED)  # لم يُرسَل بعد

        self.requester_client.post(self._url('resubmit_employment_request'))
        self.req.refresh_from_db()
        self.assertIn(self.req.status, {
            EmploymentRequest.Status.PENDING_BRANCH, EmploymentRequest.Status.PENDING_GM,
        })  # فرع بلا مدير يتجاوز المرحلة الأولى
        self.assertEqual(self.req.resubmit_count, 1)
        self.assertEqual(self.req.return_notes, 'عدّل الراتب')  # السبب يبقى للسجل

    def test_other_user_cannot_edit_or_resubmit(self):
        self._returned()
        stranger = User.objects.create_user('stranger', password='x')
        client = Client()
        client.force_login(stranger)
        client.post(self._url('edit_returned_employment_request'), {
            'name': 'اختراق', 'basic_salary': '1', 'branch': self.branch.pk,
        })
        client.post(self._url('resubmit_employment_request'))
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, EmploymentRequest.Status.RETURNED)
        self.assertEqual(self.req.name, 'مرشح للإرجاع')

    def test_edit_is_only_for_returned_requests(self):
        resp = self.requester_client.get(self._url('edit_returned_employment_request'), follow=True)
        self.assertContains(resp, 'التعديل متاح للطلب المُرتجَع فقط')

    # ── الواجهة ───────────────────────────────────────────────────────────
    def test_decision_card_has_reason_box_for_return_and_reject(self):
        page = self.admin_client.get(self._url('employment_request_detail'))
        self.assertContains(page, 'name="review_notes"')
        self.assertContains(page, self._url('return_employment_request'))
        self.assertContains(page, self._url('reject_employment_request'))

    def test_returned_hire_shows_in_requesters_returned_tab_and_inbox(self):
        self._returned()
        base = reverse('web:list_pending_actions')
        returned = self.requester_client.get(base + '?tab=returned')
        self.assertContains(returned, 'مرشح للإرجاع')
        self.assertEqual(returned.context['counts']['returned'], 1)
        inbox = self.requester_client.get(base + '?tab=inbox')
        self.assertContains(inbox, 'مرشح للإرجاع')
