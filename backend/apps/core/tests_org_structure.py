"""اختبارات تحميل تبويبات الهيكل التنظيمي."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import Branch, Company
from apps.core.services.org_structure import get_org_tab_context
from apps.departments.models import Department

User = get_user_model()


class OrgStructureTabTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة')
        cls.branch = Branch.objects.create(name='فرع', code='BR1', company=cls.company)
        cls.user = User.objects.create_superuser(username='admin_org', password='x')
        Department.objects.create(code='D1', name='قسم تقني', branch=cls.branch)

    def test_departments_tab_context_loads_without_field_error(self):
        ctx = get_org_tab_context(self.user, 'departments')
        self.assertEqual(ctx['tab'], 'departments')
        self.assertEqual(len(ctx['departments']), 1)
        self.assertEqual(ctx['departments'][0].name, 'قسم تقني')

    def test_departments_tab_http_returns_department_markup(self):
        client = Client()
        client.force_login(self.user)
        url = reverse('web:org_structure_tab') + '?tab=departments'
        response = client.get(
            url,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='127.0.0.1:8000',
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('إضافة قسم', html)
        self.assertIn('اسم القسم', html)
        self.assertNotIn('إضافة مركز تكلفة', html)
