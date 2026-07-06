"""اختبارات إدارة الصيانة."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Branch, Company, Role
from apps.maintenance.models import MaintenanceRequest, MaintenanceTrade, MaintenanceWorker
from apps.maintenance.services.access import filter_requests_for_user
from apps.maintenance.selectors.workers import assignable_maintenance_workers_qs
from apps.maintenance.services.requests import (
    MaintenanceWorkflowError,
    assign_maintenance_request,
    branch_confirm_request,
    create_maintenance_request,
    manager_close_request,
    worker_report_completion,
)

User = get_user_model()


class MaintenanceWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='شركة اختبار', commercial_record='1010101010')
        self.branch = Branch.objects.create(code='B1', name='فرع الاختبار', company=self.company)
        self.trade = MaintenanceTrade.objects.create(code='ELEC', name='كهربائي')
        self.worker = MaintenanceWorker.objects.create(
            name='عامل 1',
            phone='0512345678',
            trade=self.trade,
        )
        self.branch_mgr = User.objects.create_user(username='bm1', password='pass')
        self.maint_mgr = User.objects.create_user(username='mm1', password='pass')
        branch_role, _ = Role.objects.get_or_create(
            role_type=Role.RoleType.MANAGER,
            defaults={'name': 'مدير فرع', 'is_system_role': True},
        )
        maint_role, _ = Role.objects.get_or_create(
            role_type=Role.RoleType.MAINTENANCE_MANAGER,
            defaults={'name': 'مدير الصيانة', 'is_system_role': True},
        )
        from apps.core.models import Permission, AppModule, UserProfile

        mod, _ = AppModule.objects.get_or_create(code='maintenance', defaults={'name': 'صيانة'})
        perms = {}
        for code, op in (
            ('maintenance.view', 'view'),
            ('maintenance.add', 'add'),
            ('maintenance.assign', 'assign'),
            ('maintenance.manage', 'manage'),
            ('maintenance.confirm_branch', 'confirm_branch'),
        ):
            p, _ = Permission.objects.get_or_create(
                code=code,
                defaults={'name': code, 'module': mod, 'operation': op},
            )
            perms[code] = p
        branch_role.permissions.set([perms['maintenance.view'], perms['maintenance.add'], perms['maintenance.confirm_branch']])
        maint_role.permissions.set(perms.values())

        UserProfile.objects.update_or_create(
            user=self.branch_mgr,
            defaults={'role': branch_role, 'branch': self.branch},
        )
        UserProfile.objects.update_or_create(
            user=self.maint_mgr,
            defaults={'role': maint_role},
        )
        self.branch.manager = self.branch_mgr
        self.branch.save(update_fields=['manager'])

    def test_full_workflow(self):
        req = create_maintenance_request(
            branch=self.branch,
            title='تكييف معطل',
            description='لا يبرد',
            requested_by=self.branch_mgr,
        )
        self.assertEqual(req.status, MaintenanceRequest.Status.PENDING)

        assign_maintenance_request(request=req, worker=self.worker, assigned_by=self.maint_mgr)
        req.refresh_from_db()
        self.assertEqual(req.status, MaintenanceRequest.Status.ASSIGNED)
        self.assertTrue(req.worker_report_token)

        worker_report_completion(request=req, notes='تم الإصلاح')
        req.refresh_from_db()
        self.assertEqual(req.status, MaintenanceRequest.Status.WORKER_REPORTED)

        manager_close_request(request=req, closed_by=self.maint_mgr, notes='موافق')
        req.refresh_from_db()
        self.assertEqual(req.status, MaintenanceRequest.Status.MANAGER_CLOSED)

        branch_confirm_request(request=req, confirmed_by=self.branch_mgr)
        req.refresh_from_db()
        self.assertEqual(req.status, MaintenanceRequest.Status.BRANCH_CONFIRMED)

    def test_branch_scoping(self):
        other_branch = Branch.objects.create(code='B2', name='فرع آخر', company=self.company)
        req1 = create_maintenance_request(
            branch=self.branch, title='A', description='x', requested_by=self.branch_mgr,
        )
        create_maintenance_request(
            branch=other_branch, title='B', description='y', requested_by=self.maint_mgr,
        )
        qs_branch = filter_requests_for_user(self.branch_mgr, MaintenanceRequest.objects.all())
        self.assertEqual(qs_branch.count(), 1)
        self.assertEqual(qs_branch.first().id, req1.id)
        qs_maint = filter_requests_for_user(
            User.objects.select_related('profile__role').get(pk=self.maint_mgr.pk),
            MaintenanceRequest.objects.all(),
        )
        self.assertEqual(qs_maint.count(), 2)

    def test_assign_requires_phone(self):
        req = create_maintenance_request(
            branch=self.branch, title='X', description='y', requested_by=self.branch_mgr,
        )
        bad_worker = MaintenanceWorker.objects.create(name='بدون جوال', phone='', trade=self.trade)
        with self.assertRaises(MaintenanceWorkflowError):
            assign_maintenance_request(request=req, worker=bad_worker, assigned_by=self.maint_mgr)

    def test_assignable_workers_queryset(self):
        self.assertEqual(assignable_maintenance_workers_qs().count(), 1)
        inactive = MaintenanceWorker.objects.create(
            name='غير نشط', phone='0599999999', trade=self.trade, is_active=False,
        )
        self.assertEqual(assignable_maintenance_workers_qs().count(), 1)
        self.assertNotIn(inactive.pk, assignable_maintenance_workers_qs().values_list('pk', flat=True))
        no_phone = MaintenanceWorker.objects.create(name='بلا جوال', phone='', trade=self.trade)
        self.assertNotIn(no_phone.pk, assignable_maintenance_workers_qs().values_list('pk', flat=True))

    def test_maintenance_sub_permission_expansion(self):
        from apps.core.decorators import get_user_permissions
        from apps.core.models import AppModule, Permission, UserProfile

        mod, _ = AppModule.objects.get_or_create(
            code='maintenance_screen_assign',
            defaults={'name': 'صيانة — إسناد الطلبات', 'icon': 'wrench', 'order': 143, 'is_active': True},
        )
        perm, _ = Permission.objects.get_or_create(
            code='maintenance_screen_assign.view',
            defaults={
                'name': 'صيانة — إسناد الطلبات',
                'module': mod,
                'operation': 'view',
                'is_active': True,
            },
        )

        limited = User.objects.create_user(username='maint_assign_only', password='pass')
        limited_role = Role.objects.create(
            name='محدود صيانة اختبار',
            role_type=Role.RoleType.EMPLOYEE,
            is_system_role=False,
        )
        limited_role.permissions.set([perm])
        UserProfile.objects.update_or_create(user=limited, defaults={'role': limited_role})
        limited = User.objects.select_related('profile__role').get(pk=limited.pk)

        codes = get_user_permissions(limited)
        self.assertIn('maintenance_screen_assign.view', codes)
        self.assertIn('maintenance.assign', codes)
        self.assertNotIn('maintenance.view', codes)
