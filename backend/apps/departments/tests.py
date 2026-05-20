from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Branch, Company, UserProfile
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department

User = get_user_model()


class DepartmentModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة اختبار')
        cls.branch = Branch.objects.create(
            name='فرع جدة', code='DEPT-TST', company=cls.company,
        )
        cls.cost_center = CostCenter.objects.create(
            code='CC-D', name='مركز تكلفة', branch=cls.branch,
        )

    def test_str_includes_code_and_name(self):
        dept = Department.objects.create(
            code='HR-01', name='الموارد البشرية', branch=self.branch,
        )
        self.assertEqual(str(dept), 'HR-01 - الموارد البشرية')

    def test_cost_center_optional(self):
        dept = Department.objects.create(
            code='HR-02', name='المالية', branch=self.branch, cost_center=self.cost_center,
        )
        self.assertEqual(dept.cost_center_id, self.cost_center.pk)

    def test_employees_count_without_employees(self):
        dept = Department.objects.create(code='HR-03', name='فارغ', branch=self.branch)
        self.assertEqual(dept.employees_count, 0)
