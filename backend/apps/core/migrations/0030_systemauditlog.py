from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0029_deactivate_legacy_attendance_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='الوقت')),
                ('action', models.CharField(
                    choices=[
                        ('password_change_self', 'تغيير كلمة المرور (ذاتي)'),
                        ('password_change_admin', 'تعيين كلمة مرور (مدير)'),
                        ('user_login', 'تسجيل دخول'),
                    ],
                    db_index=True,
                    max_length=40,
                    verbose_name='رمز العملية',
                )),
                ('summary', models.CharField(max_length=255, verbose_name='العملية')),
                ('details', models.TextField(blank=True, verbose_name='التفاصيل التقنية')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='عنوان IP')),
                ('actor', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='system_audit_actions',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='المنفّذ',
                )),
                ('target_user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='system_audit_targets',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='المستخدم المستهدف',
                )),
            ],
            options={
                'verbose_name': 'سجل عملية نظام',
                'verbose_name_plural': 'سجل عمليات النظام',
                'ordering': ['-created_at'],
            },
        ),
    ]
