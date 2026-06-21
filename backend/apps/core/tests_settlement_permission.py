"""اختبارات صلاحية تنفيذ تصفية نهاية خدمة / استقالة."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.decorators import get_user_permissions
from apps.core.employee_tab_permissions import (
    SETTLEMENT_EXECUTE_PERMISSION,
    user_can_execute_settlement,
)
from apps.core.models import Permission, Role, UserProfile

User = get_user_model()


class SettlementExecutePermissionTests(TestCase):
    def setUp(self):
        self.execute_perm = Permission.objects.get(code=SETTLEMENT_EXECUTE_PERMISSION)
        self.role_hr_officer = Role.objects.create(
            name='HR Officer Test',
            role_type=Role.RoleType.HR_OFFICER,
            is_system_role=True,
        )
        self.role_hr_manager = Role.objects.create(
            name='HR Manager Test',
            role_type=Role.RoleType.HR_MANAGER,
            is_system_role=True,
        )
        self.role_hr_manager.permissions.add(self.execute_perm)

    def _user_with_role(self, username, role, *, extra_perms=None):
        user = User.objects.create_user(username=username, password='x')
        profile = UserProfile.objects.get(user=user)
        profile.role = role
        profile.save(update_fields=['role', 'updated_at'])
        if extra_perms:
            profile.extra_permissions.add(*extra_perms)
        return User.objects.select_related('profile__role').get(pk=user.pk)

    def test_hr_manager_can_execute_by_default(self):
        user = self._user_with_role('hr_mgr', self.role_hr_manager)
        self.assertIn(SETTLEMENT_EXECUTE_PERMISSION, get_user_permissions(user))
        self.assertTrue(user_can_execute_settlement(user))

    def test_hr_officer_denied_without_explicit_grant(self):
        user = self._user_with_role('hr_off', self.role_hr_officer)
        self.assertNotIn(SETTLEMENT_EXECUTE_PERMISSION, get_user_permissions(user))
        self.assertFalse(user_can_execute_settlement(user))

    def test_hr_officer_allowed_with_extra_permission(self):
        user = self._user_with_role(
            'hr_off_granted',
            self.role_hr_officer,
            extra_perms=[self.execute_perm],
        )
        self.assertIn(SETTLEMENT_EXECUTE_PERMISSION, get_user_permissions(user))
        self.assertTrue(user_can_execute_settlement(user))
