"""
مستخدم إدارة أولي — يُنشأ مرة واحدة عند أول نشر فقط.

إذا وُجد username في قاعدة البيانات: لا يُعاد إنشاؤه ولا تُغيَّر كلمة المرور.

متغيرات البيئة:
  DJANGO_SUPERUSER_USERNAME  (افتراضي: admin)
  DJANGO_SUPERUSER_PASSWORD  (مطلوب للإنشاء الأول فقط)
  DJANGO_SUPERUSER_EMAIL
"""
from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Ensure bootstrap superuser exists once (skip if already in DB)'

    def handle(self, *args, **options):
        User = get_user_model()
        username = (os.environ.get('DJANGO_SUPERUSER_USERNAME') or 'admin').strip()
        password = (os.environ.get('DJANGO_SUPERUSER_PASSWORD') or '').strip()
        email = (os.environ.get('DJANGO_SUPERUSER_EMAIL') or 'admin@example.com').strip()

        if not username:
            self.stdout.write(self.style.WARNING('DJANGO_SUPERUSER_USERNAME فارغ — تخطي.'))
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                f"مستخدم «{username}» موجود مسبقاً — لم يُعد إنشاؤه (كلمة المرور كما هي)."
            )
            return

        if not password:
            self.stdout.write(
                self.style.WARNING(
                    'DJANGO_SUPERUSER_PASSWORD غير مضبوط — تخطي إنشاء المستخدم الأولي. '
                    'اضبطه في Dokploy قبل أول نشر.'
                )
            )
            return

        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(
            self.style.SUCCESS(f'تم إنشاء مستخدم الإدارة «{username}» (مرة واحدة فقط).')
        )

        try:
            from apps.core.models import Role, UserProfile

            admin_role = Role.objects.filter(
                role_type=Role.RoleType.ADMIN,
                is_deleted=False,
            ).first()
            if admin_role:
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if profile.role_id != admin_role.pk:
                    profile.role = admin_role
                    profile.save(update_fields=['role', 'updated_at'])
                self.stdout.write(f'تم ربط «{username}» بدور الأدمن.')
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(f'تعذّر ربط دور الأدمن (غير حرج): {exc}')
            )
