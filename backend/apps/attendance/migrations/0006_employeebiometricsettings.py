from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0027_employee_meal_allowance'),
        ('attendance', '0005_attendancepunch_uniq_fingerprint'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmployeeBiometricSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='محذوف')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف')),
                ('expected_check_in', models.TimeField(blank=True, help_text='بصمات الدخول بعد هذا الوقت + فترة السماح لا تُعرض في تبويب البصمة.', null=True, verbose_name='وقت الدخول المتوقع')),
                ('expected_check_out', models.TimeField(blank=True, help_text='للمرجعية — يُستخدم لاحقاً في التقارير.', null=True, verbose_name='وقت الخروج المتوقع')),
                ('late_grace_minutes', models.PositiveSmallIntegerField(default=30, help_text='بعد وقت الدخول + هذه الدقائق تُخفى بصمات الدخول المتأخرة.', verbose_name='سماح التأخير (دقيقة)')),
                ('employee', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='biometric_settings', to='employees.employee', verbose_name='الموظف')),
            ],
            options={
                'verbose_name': 'إعدادات بصمة الموظف',
                'verbose_name_plural': 'إعدادات بصمات الموظفين',
            },
        ),
    ]
