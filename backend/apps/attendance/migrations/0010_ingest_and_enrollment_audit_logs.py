# Generated manually for phase-3 security audit

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0033_recalc_absence_30_day_rule'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('attendance', '0009_attendancepunch_report_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceIngestLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('is_deleted', models.BooleanField(db_index=True, default=False, verbose_name='محذوف')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف')),
                ('agent_id', models.CharField(blank=True, default='', max_length=120, verbose_name='معرّف الوكيل')),
                ('status', models.CharField(choices=[('success', 'نجاح'), ('rejected_signature', 'توقيع مرفوض'), ('rejected_payload', 'حمولة مرفوضة'), ('error', 'خطأ')], db_index=True, max_length=32, verbose_name='الحالة')),
                ('signature_valid', models.BooleanField(blank=True, null=True, verbose_name='توقيع صالح')),
                ('punches_received', models.PositiveIntegerField(default=0, verbose_name='بصمات مستلمة')),
                ('imported', models.PositiveIntegerField(default=0, verbose_name='بصمات جديدة')),
                ('skipped_duplicate', models.PositiveIntegerField(default=0, verbose_name='مكررة')),
                ('skipped_time_filter', models.PositiveIntegerField(default=0, verbose_name='مرفوضة زمنياً')),
                ('users_updated', models.PositiveIntegerField(default=0, verbose_name='مستخدمون محدّثون')),
                ('message', models.TextField(blank=True, default='', verbose_name='رسالة')),
                ('client_ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='عنوان IP')),
                ('user_agent', models.CharField(blank=True, default='', max_length=255, verbose_name='وكيل المستخدم')),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ingest_logs', to='attendance.biometricdevice', verbose_name='الجهاز')),
            ],
            options={
                'verbose_name': 'سجل استقبال بصمات',
                'verbose_name_plural': 'سجلات استقبال البصمات',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='BiometricEnrollmentAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('is_deleted', models.BooleanField(db_index=True, default=False, verbose_name='محذوف')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف')),
                ('device_user_id', models.PositiveIntegerField(db_index=True, verbose_name='رقم المستخدم على الجهاز')),
                ('device_user_name', models.CharField(blank=True, default='', max_length=120, verbose_name='اسم المستخدم على الجهاز')),
                ('action', models.CharField(choices=[('create', 'ربط جديد'), ('reassign', 'إعادة ربط'), ('update', 'تحديث')], max_length=16, verbose_name='الإجراء')),
                ('punches_relinked', models.PositiveIntegerField(default=0, verbose_name='بصمات أُعيد ربطها')),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrollment_audit_logs', to='attendance.biometricdevice', verbose_name='الجهاز')),
                ('new_employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='biometric_enrollment_audit', to='employees.employee', verbose_name='الموظف الجديد')),
                ('performed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='biometric_enrollment_audits', to=settings.AUTH_USER_MODEL, verbose_name='نُفّذ بواسطة')),
                ('previous_employee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='biometric_enrollment_replaced_audit', to='employees.employee', verbose_name='الموظف السابق')),
            ],
            options={
                'verbose_name': 'تدقيق ربط بصمة',
                'verbose_name_plural': 'تدقيق ربط البصمات',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='attendanceingestlog',
            index=models.Index(fields=['-created_at'], name='attendance__created_6a8f2d_idx'),
        ),
        migrations.AddIndex(
            model_name='attendanceingestlog',
            index=models.Index(fields=['device', '-created_at'], name='attendance__device__f3c1a9_idx'),
        ),
        migrations.AddIndex(
            model_name='attendanceingestlog',
            index=models.Index(fields=['status', '-created_at'], name='attendance__status__8b4e21_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricenrollmentauditlog',
            index=models.Index(fields=['device', 'device_user_id', '-created_at'], name='attendance__device__a1b2c3_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricenrollmentauditlog',
            index=models.Index(fields=['new_employee', '-created_at'], name='attendance__new_emp_4d5e6f_idx'),
        ),
    ]
