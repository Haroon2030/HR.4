"""تعديل خصومات التصفية ورفع الملف الموقّع قبل الموافقة النهائية."""
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import Client, TestCase, override_settings

from apps.core.models import Branch, Company, PendingAction, Role, UserProfile
from apps.core.services import pending_actions as svc
from apps.employees.models import Employee
from apps.employees.services.settlement_financials import net_settlement_total
from apps.employees.services.settlement_override import (
    apply_override_to_financials,
    apply_override_to_form_context,
    parse_override_post,
)

User = get_user_model()
PDF = b'%PDF-1.4\n%%EOF'


def _post(**fields):
    data = QueryDict(mutable=True)
    for key, value in fields.items():
        if isinstance(value, (list, tuple)):
            data.setlist(key, list(value))
        else:
            data[key] = value
    return data


BASE = {
    'prorated_salary': Decimal('1000.00'),
    'loans_deduction': Decimal('300.00'),
    'absences_deduction': Decimal('0'),
    'penalties_deduction': Decimal('0'),
    'cash_shortages_deduction': Decimal('0'),
    'overpaid_salary_recovery': Decimal('0'),
    'total_deductions': Decimal('300.00'),
}


class OverrideServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ovuser', password='x')

    def test_unchanged_values_produce_no_override(self):
        override, errors = parse_override_post(_post(ov_loans_deduction='300.00'), self.user, BASE)
        self.assertEqual((override, errors), ({}, []))

    def test_change_requires_reason(self):
        _, errors = parse_override_post(_post(ov_loans_deduction='100'), self.user, BASE)
        self.assertTrue(any('سبب' in e for e in errors))

    def test_change_with_reason_and_manual_items(self):
        override, errors = parse_override_post(_post(
            ov_loans_deduction='100', ov_reason='اتفاق مع الموظف',
            manual_label=['تأمين طبي', ''], manual_amount=['50', ''], manual_kind=['deduction', 'deduction'],
        ), self.user, BASE)
        self.assertEqual(errors, [])
        self.assertEqual(override['loans_deduction'], '100.00')
        self.assertEqual(override['manual_items'], [{'label': 'تأمين طبي', 'amount': '50.00', 'kind': 'deduction'}])
        fin = apply_override_to_financials(BASE, override)
        self.assertEqual(fin['total_deductions'], Decimal('150.00'))  # 100 سلف + 50 يدوي

    def test_negative_and_bad_values_rejected(self):
        _, errors = parse_override_post(_post(ov_loans_deduction='-5', ov_reason='x'), self.user, BASE)
        self.assertTrue(errors)
        _, errors = parse_override_post(_post(ov_loans_deduction='abc', ov_reason='x'), self.user, BASE)
        self.assertTrue(errors)

    def test_manual_item_needs_label_and_amount(self):
        _, errors = parse_override_post(_post(
            ov_reason='x', manual_label=['بند'], manual_amount=[''], manual_kind=['deduction'],
        ), self.user, BASE)
        self.assertTrue(errors)

    def test_net_includes_manual_addition_and_deduction(self):
        override, _ = parse_override_post(_post(
            ov_reason='x', manual_label=['حافز', 'غرامة'], manual_amount=['200', '50'],
            manual_kind=['addition', 'deduction'],
        ), self.user, BASE)
        fin = apply_override_to_financials(BASE, override)
        net = net_settlement_total(eosb=Decimal('0'), leave_comp=Decimal('0'), penalty=Decimal('0'), financials=fin)
        # 1000 راتب + 200 إضافي − (300 سلف + 50 يدوي) = 850
        self.assertEqual(net, Decimal('850.00'))

    def test_form_context_recomputed(self):
        override, _ = parse_override_post(_post(ov_loans_deduction='100', ov_reason='x'), self.user, BASE)
        ctx = apply_override_to_form_context(
            {'prorated_salary': '1000', 'loans_deduction': '300', 'eosb_amount': '500', 'leave_comp': '100'},
            override,
        )
        self.assertEqual(ctx['loans_deduction'], '100.00')
        self.assertEqual(ctx['total_entitlement'], '1500.00')  # 500 + 100 + 1000 − 100


class FormSlotsTests(TestCase):
    CTX = {'prorated_salary': '1000', 'loans_deduction': '300', 'eosb_amount': '0', 'leave_comp': '0'}

    def test_other_and_manual_deductions_fill_form_rows_without_double_count(self):
        override = {
            'penalties_deduction': '50.00',
            'manual_items': [
                {'label': 'تأمين', 'amount': '25.00', 'kind': 'deduction'},
                {'label': 'مكافأة', 'amount': '100.00', 'kind': 'addition'},
            ],
            'reason': 'x',
        }
        ctx = apply_override_to_form_context(dict(self.CTX), override)
        slots = ctx['deduction_slots']
        self.assertEqual([s['amount'] for s in slots], ['50.00', '25.00', ''])
        self.assertEqual(slots[0]['label'], 'مخالفات غير محتسبة')
        self.assertEqual(slots[1]['label'], 'تأمين')
        # 1000 راتب + 100 استحقاق − 300 سلف − 75 (صفوف الخصم) = 725
        self.assertEqual(ctx['total_entitlement'], '725.00')
        # أساس السكربت = الصافي قبل صفوف الخصم، فلا يُطرح الخصم مرتين
        self.assertEqual(ctx['net_base'], '800.00')
        self.assertEqual([i['label'] for i in ctx['manual_additions_items']], ['مكافأة'])

    def test_more_than_three_entries_are_merged_into_last_row(self):
        override = {
            'manual_items': [{'label': f'بند{i}', 'amount': '10.00', 'kind': 'deduction'} for i in range(1, 5)],
            'reason': 'x',
        }
        ctx = apply_override_to_form_context(dict(self.CTX), override)
        amounts = [s['amount'] for s in ctx['deduction_slots']]
        self.assertEqual(amounts, ['10.00', '10.00', '20.00'])
        self.assertIn('بند3', ctx['deduction_slots'][2]['label'])
        self.assertIn('بند4', ctx['deduction_slots'][2]['label'])
        self.assertEqual(ctx['total_entitlement'], '660.00')  # 1000 − 300 − 40


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class SettlementEditFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('adm', password='x', is_superuser=True, is_staff=True)
        company = Company.objects.create(name='شركة الاختبار')
        branch = Branch.objects.create(name='فرع الاختبار', code='OV1', company=company)
        self.emp = Employee.objects.create(
            name='موظف تصفية', hire_date=date.today() - timedelta(days=400), basic_salary=Decimal('3000'),
            branch=branch,
        )
        self.action = svc.submit_settlement_for_approval(
            action_type='terminate', employee=self.emp,
            payload={'end_date': date.today().isoformat(), 'end_reason': 'x'},
            requested_by=self.admin,
        )
        officer_role = Role.objects.create(
            name='Officer OV', role_type=Role.RoleType.HR_OFFICER, is_system_role=True,
        )
        officer = User.objects.create_user('ovofficer', password='x')
        profile = UserProfile.objects.get(user=officer)
        profile.role = officer_role
        profile.save(update_fields=['role', 'updated_at'])
        officer = User.objects.select_related('profile__role').get(pk=officer.pk)
        svc.gm_approve_and_assign(self.action, self.admin, officer)
        self.action.refresh_from_db()
        self.client = Client()
        self.client.force_login(self.admin)

    def _url(self, name):
        from django.urls import reverse
        return reverse(f'web:{name}', args=[self.action.id])

    def test_approval_blocked_without_signed_file(self):
        with self.assertRaises(ValueError):
            svc.officer_approve(self.action, self.admin)
        self.client.post(self._url('officer_approve_action'))
        self.action.refresh_from_db()
        self.assertNotEqual(self.action.status, PendingAction.Status.APPROVED)
        self.assertFalse(self.action.executed_at)

    def test_upload_then_approve(self):
        pdf = SimpleUploadedFile('signed.pdf', PDF, content_type='application/pdf')
        self.client.post(self._url('settlement_signed_upload'), {'signed_file': pdf})
        self.action.refresh_from_db()
        self.assertTrue(self.action.signed_settlement)
        self.client.post(self._url('officer_approve_action'))
        self.action.refresh_from_db()
        self.assertTrue(self.action.executed_at)

    def test_bad_upload_rejected(self):
        bad = SimpleUploadedFile('x.exe', b'MZ', content_type='application/octet-stream')
        self.client.post(self._url('settlement_signed_upload'), {'signed_file': bad})
        self.action.refresh_from_db()
        self.assertFalse(self.action.signed_settlement)

    def test_edit_saved_and_invalidates_signed_file(self):
        self.client.post(self._url('settlement_signed_upload'), {
            'signed_file': SimpleUploadedFile('signed.pdf', PDF, content_type='application/pdf'),
        })
        self.client.post(self._url('settlement_edit_action'), {
            'ov_reason': 'خصم متفق عليه',
            'manual_label': ['تأمين'], 'manual_amount': ['75'], 'manual_kind': ['deduction'],
        })
        self.action.refresh_from_db()
        override = self.action.payload['settlement_override']
        self.assertEqual(override['manual_items'][0]['amount'], '75.00')
        self.assertEqual(override['reason'], 'خصم متفق عليه')
        self.assertFalse(self.action.signed_settlement)  # التوقيع القديم لم يعد مطابقاً

    def test_edit_without_reason_not_saved(self):
        self.client.post(self._url('settlement_edit_action'), {
            'manual_label': ['تأمين'], 'manual_amount': ['75'], 'manual_kind': ['deduction'],
        })
        self.action.refresh_from_db()
        self.assertNotIn('settlement_override', self.action.payload)

    def test_non_officer_cannot_edit(self):
        other = User.objects.create_user('plain', password='x')
        client = Client()
        client.force_login(other)
        client.post(self._url('settlement_edit_action'), {
            'ov_reason': 'x', 'manual_label': ['a'], 'manual_amount': ['1'], 'manual_kind': ['deduction'],
        })
        self.action.refresh_from_db()
        self.assertNotIn('settlement_override', self.action.payload)

    def test_detail_page_shows_panel_and_print_preview_applies_override(self):
        self.client.post(self._url('settlement_edit_action'), {
            'ov_reason': 'سبب', 'manual_label': ['بند خاص'], 'manual_amount': ['40'], 'manual_kind': ['deduction'],
        })
        page = self.client.get(self._url('pending_action_detail'))
        self.assertContains(page, 'تعديل التصفية قبل التوقيع')
        self.assertContains(page, 'بند خاص')
        from django.urls import reverse
        form = self.client.get(
            reverse('web:hr_form_print', args=['final_settlement', self.emp.id]) + f'?action={self.action.id}'
        )
        self.assertContains(form, 'بند خاص')
        self.assertContains(form, 'سبب')
