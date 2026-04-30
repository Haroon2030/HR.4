"""
إنشاء UserProfile للمستخدمين الموجودين وربطهم بالأدوار
python manage.py setup_user_profiles
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.core.models import UserProfile, Role

User = get_user_model()


class Command(BaseCommand):
    help = 'إنشاء UserProfile للمستخدمين الموجودين الذين ليس لديهم profile'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('🔧 جاري إعداد UserProfile للمستخدمين...'))
        
        # الحصول على دور الأدمن
        try:
            admin_role = Role.objects.get(role_type=Role.RoleType.ADMIN)
        except Role.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ لا يوجد دور أدمن في النظام! قم بتشغيل: python manage.py setup_permissions_and_roles'))
            return
        
        # الحصول على جميع المستخدمين
        users = User.objects.all()
        created_count = 0
        updated_count = 0
        
        for user in users:
            # التحقق من وجود profile
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'phone': '',
                    'department': '',
                    'position': '',
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(f'  ✓ تم إنشاء profile للمستخدم: {user.username}')
            
            # إذا كان المستخدم superuser، ربطه بدور الأدمن
            if user.is_superuser and profile.role != admin_role:
                profile.role = admin_role
                profile.save()
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ تم ربط {user.username} بدور الأدمن'))
        
        self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء {created_count} profile جديد'))
        self.stdout.write(self.style.SUCCESS(f'✅ تم تحديث {updated_count} مستخدم بدور الأدمن'))
        self.stdout.write(self.style.SUCCESS('✅ اكتمل الإعداد بنجاح!'))
