"""دخان شاشات الويب الأساسية: قائمة / إضافة / فرع / رواتب / طلبات."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.core.models import Branch, Company, Role
from apps.employees.models import Employee

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class WebScreensSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name='شركة دخان',
            tax_number='900',
            commercial_record='900',
        )
        cls.branch = Branch.objects.create(
            name='فرع دخان',
            code='SMK',
            company=cls.company,
        )
        cls.admin_role = Role.objects.create(
            name='أدمن دخان',
            role_type=Role.RoleType.ADMIN,
            is_system_role=True,
        )
        cls.admin = User.objects.create_user(username='smoke_admin', password='654321')
        profile = cls.admin.profile
        profile.role = cls.admin_role
        profile.branch = cls.branch
        profile.save(update_fields=['role', 'branch'])
        profile.assigned_branches.add(cls.branch)

        cls.employee = Employee.objects.create(
            name='موظف دخان',
            branch=cls.branch,
            employee_number='SMK-001',
            status=Employee.Status.ACTIVE,
        )

    def setUp(self):
        self.client = Client()
        self.assertTrue(self.client.login(username='smoke_admin', password='654321'))

    def _assert_reachable(self, name, *, kwargs=None, allow_redirect=False):
        """200 = شاشة، أو 302 مقصود (فلاتر/توجيه) ثم وجهة نهائية 200."""
        url = reverse(f'web:{name}', kwargs=kwargs or {})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200, msg=f'{name} → {response.status_code}')
        if not allow_redirect:
            self.assertFalse(response.redirect_chain, msg=f'{name} redirected unexpectedly')
        return response

    def test_dashboard_and_lists(self):
        self._assert_reachable('dashboard')
        self._assert_reachable('list_employees')
        self._assert_reachable('list_branches')
        self._assert_reachable('list_payroll_runs', allow_redirect=True)
        self._assert_reachable('list_pending_actions')
        self._assert_reachable('list_cash_shortages')
        self._assert_reachable('reports_index')
        self._assert_reachable('maintenance_setup')

    def test_add_screens_render(self):
        self._assert_reachable('add_employee')
        self._assert_reachable('add_branch')
        # التسجيل عبر POST فقط — GET يوجّه لقائمة العجز حيث النموذج
        self._assert_reachable('register_cash_shortage', allow_redirect=True)

    def test_employee_and_branch_detail(self):
        self._assert_reachable('view_employee', kwargs={'employee_id': self.employee.id})
        self._assert_reachable('edit_branch', kwargs={'branch_id': self.branch.id})

    def test_dead_routes_are_gone(self):
        from django.urls import NoReverseMatch

        for name in (
            'create_payroll_run',
            'multi_report_detail',
            'run_ledger_init',
            'approve_pending_action',
            'list_maintenance_trades',
            'download_database_backup',
            'add_employee_business_trip',
            'employee_barcode_print_batch',
        ):
            with self.assertRaises(NoReverseMatch, msg=name):
                reverse(f'web:{name}')
