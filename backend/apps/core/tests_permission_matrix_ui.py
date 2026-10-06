"""قائمة الصلاحيات المضغوطة (أقراص بدل أعمدة) — صفحتا الدور والمستخدم."""
from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse

from apps.core.decorators import get_user_permissions
from apps.core.models import Permission, Role

User = get_user_model()


class PermissionListPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username='root', password='Pass-User-99!', email='r@e.co')
        cls.role = Role.objects.create(name='Spec', role_type=Role.RoleType.SPECIALIST)
        cls.view_perm = Permission.objects.get(code='employees.view')
        cls.add_perm = Permission.objects.get(code='employees.add')
        cls.edit_perm = Permission.objects.get(code='employees.edit')
        cls.role.permissions.set([cls.view_perm, cls.edit_perm])
        cls.target = User.objects.create_user(username='target', password='Pass-User-99!')
        cls.target.profile.role = cls.role
        cls.target.profile.save()

    def setUp(self):
        self.client.force_login(self.admin)

    def test_user_page_renders_chips_not_table_columns(self):
        response = self.client.get(reverse('web:manage_user_permissions', args=[self.target.id]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('hr-perm-chip', html)
        self.assertNotIn('hr-perm-erp-table', html)
        # كل صلاحية فعّالة لها قرص واحد على الأكثر (لا خلايا فارغة لعمليات غير موجودة)
        self.assertRegex(html, rf'name="perm_{self.view_perm.id}"\s+value="allowed"')
        self.assertNotIn('hr-perm-empty', html)

    def test_role_page_renders_chips(self):
        response = self.client.get(reverse('web:manage_role_permissions', args=[self.role.id]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('hr-perm-chip', html)
        self.assertNotIn('hr-perm-erp-table', html)

    def test_chip_post_format_grants_and_denies(self):
        """القرص يُرسل denied (مخفي) ثم allowed إن كان محدَّداً — والأخير يغلب."""
        data = QueryDict(mutable=True)
        # view: ممنوح من الدور ويبقى محدداً → inherit
        data.setlist(f'perm_{self.view_perm.id}', ['denied', 'allowed'])
        # add: خارج الدور وحُدِّد → منح إضافي للمستخدم
        data.setlist(f'perm_{self.add_perm.id}', ['denied', 'allowed'])
        # edit: داخل الدور وأُلغي تحديده → حجب عن المستخدم
        data.setlist(f'perm_{self.edit_perm.id}', ['denied'])
        self.client.post(reverse('web:manage_user_permissions', args=[self.target.id]), data)

        user = User.objects.get(pk=self.target.pk)
        perms = get_user_permissions(user)
        self.assertIn('employees.view', perms)
        self.assertIn('employees.add', perms)
        self.assertNotIn('employees.edit', perms)
