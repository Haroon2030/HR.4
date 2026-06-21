"""
تحويل unique constraints على EmployeeBiometricEnrollment إلى partial:
تسري فقط على السجلات النشطة (is_deleted=False).
هذا يحل مشكلة تعارض الـ constraint عند soft-delete وإعادة الربط.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0011_biometricpullrequest'),
    ]

    operations = [
        # إزالة الـ constraints الكاملة القديمة
        migrations.RemoveConstraint(
            model_name='employeebiometricenrollment',
            name='uniq_device_user_per_device',
        ),
        migrations.RemoveConstraint(
            model_name='employeebiometricenrollment',
            name='uniq_employee_per_device',
        ),
        # إضافة partial unique constraints (تسري فقط عند is_deleted=False)
        migrations.AddConstraint(
            model_name='employeebiometricenrollment',
            constraint=models.UniqueConstraint(
                fields=['device', 'device_user_id'],
                condition=models.Q(is_deleted=False),
                name='uniq_device_user_per_device_active',
            ),
        ),
        migrations.AddConstraint(
            model_name='employeebiometricenrollment',
            constraint=models.UniqueConstraint(
                fields=['device', 'employee'],
                condition=models.Q(is_deleted=False),
                name='uniq_employee_per_device_active',
            ),
        ),
    ]
