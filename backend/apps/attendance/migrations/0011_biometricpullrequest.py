# Generated manually — طلبات سحب البصمة في قاعدة البيانات

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('attendance', '0010_ingest_and_enrollment_audit_logs'),
    ]

    operations = [
        migrations.CreateModel(
            name='BiometricPullRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('is_deleted', models.BooleanField(db_index=True, default=False, verbose_name='محذوف')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الحذف')),
                ('date_from', models.DateField(blank=True, null=True, verbose_name='من تاريخ')),
                ('date_to', models.DateField(blank=True, null=True, verbose_name='إلى تاريخ')),
                ('acknowledged_at', models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='تم التنفيذ')),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pull_requests', to='attendance.biometricdevice', verbose_name='الجهاز')),
                ('requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='biometric_pull_requests', to=settings.AUTH_USER_MODEL, verbose_name='طُلب بواسطة')),
            ],
            options={
                'verbose_name': 'طلب سحب بصمة',
                'verbose_name_plural': 'طلبات سحب البصمة',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='biometricpullrequest',
            index=models.Index(fields=['device', 'acknowledged_at', '-created_at'], name='attendance__device__pull_idx'),
        ),
    ]
