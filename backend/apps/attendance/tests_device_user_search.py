from django.db.models import Count, Q
from django.test import TestCase

from apps.attendance.models import BiometricDevice, BiometricDeviceUser, EmployeeBiometricEnrollment
from apps.attendance.selectors.device_users import get_device_user_queryset
from apps.core.models import Branch, Company
from apps.employees.models import Employee


class DeviceUserSearchTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='شركة')
        self.br = Branch.objects.create(name='حائل', code='HAIL', company=company, is_active=True)
        self.dev = BiometricDevice.objects.create(
            name='حائل',
            branch=self.br,
            ip_address='10.0.0.5',
            port=4370,
            is_active=True,
        )
        BiometricDeviceUser.objects.create(device=self.dev, device_user_id=78, name='على الجهاز')
        BiometricDeviceUser.objects.create(device=self.dev, device_user_id=10078, name='مستخدم 10078')
        self.emp = Employee.objects.create(
            employee_number='10078',
            name='موظف حائل',
            branch=self.br,
            status='active',
        )
        EmployeeBiometricEnrollment.objects.create(
            device=self.dev,
            device_user_id=78,
            employee=self.emp,
            device_user_name='على الجهاز',
        )

    def test_search_by_employee_number_finds_enrolled_zk_id(self):
        qs = get_device_user_queryset(device_id=self.dev.id, search='10078')
        ids = set(qs.values_list('device_user_id', flat=True))
        self.assertIn(78, ids)
        self.assertIn(10078, ids)
        stats = qs.aggregate(
            total=Count('pk'),
            unmapped=Count('pk', filter=Q(is_hr_linked=False)),
        )
        self.assertEqual(stats['total'], 2)

    def test_search_by_zk_id_only(self):
        qs = get_device_user_queryset(device_id=self.dev.id, search='78')
        ids = set(qs.values_list('device_user_id', flat=True))
        self.assertIn(78, ids)
