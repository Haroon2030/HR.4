from decimal import Decimal

from django.test import TestCase

from apps.core.models import Branch, Company
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


class CostCenterModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='شركة اختبار')
        cls.branch = Branch.objects.create(
            name='فرع الرياض', code='CC-TST', company=cls.company,
        )

    def test_str_and_branch_link(self):
        cc = CostCenter.objects.create(
            code='CC-01', name='مركز إنتاج', branch=self.branch, budget=Decimal('100000'),
        )
        self.assertEqual(str(cc), 'CC-01 - مركز إنتاج')
        self.assertEqual(cc.branch_id, self.branch.pk)

    def test_departments_count_excludes_deleted(self):
        cc = CostCenter.objects.create(code='CC-02', name='مركز ثانوي', branch=self.branch)
        Department.objects.create(code='D-01', name='قسم أ', branch=self.branch, cost_center=cc)
        deleted = Department.objects.create(
            code='D-02', name='قسم محذوف', branch=self.branch, cost_center=cc,
        )
        deleted.delete()
        self.assertEqual(cc.departments_count, 1)
