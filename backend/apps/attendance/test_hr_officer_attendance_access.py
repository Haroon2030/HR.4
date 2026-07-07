"""اختبارات وصول أخصائي الموارد لسجلات البصمة."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.core.models import Branch, Company, Permission, Role

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class HrOfficerAttendanceRecordsAccessTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة اختبار')
        self.branch = Branch.objects.create(name='فرع 1', code='TBR1', company=company)
        Branch.objects.create(name='فرع 2', code='TBR2', company=company)

        self.role = Role.objects.create(
            name='HR Officer Test',
            role_type=Role.RoleType.HR_OFFICER,
            is_system_role=True,
            is_active=True,
        )
        perm, _ = Permission.objects.get_or_create(
            code='attendance.view',
            defaults={'name': 'عرض البصمة', 'operation': 'view', 'is_active': True},
        )
        perm.is_active = True
        perm.save(update_fields=['is_active'])
        self.role.permissions.add(perm)

        emp_perm, _ = Permission.objects.get_or_create(
            code='employees.view',
            defaults={'name': 'عرض الموظفين', 'operation': 'view', 'is_active': True},
        )
        self.role.permissions.add(emp_perm)

        self.user = User.objects.create_user(username='hr_officer_test', password='test-pass-99')
        profile = self.user.profile
        profile.role = self.role
        profile.branch = self.branch
        profile.save(update_fields=['role', 'branch'])

    def test_hr_officer_has_company_wide_branch_access(self):
        from apps.core.services.access_control import get_accessible_branch_ids

        self.assertIsNone(get_accessible_branch_ids(self.user))

    def test_attendance_records_page_loads_for_hr_officer(self):
        client = Client()
        client.force_login(self.user)
        response = client.get('/attendance/records/')
        self.assertEqual(response.status_code, 200, response.content[:500])
