"""
أمر لمزامنة الوحدات والصلاحيات تلقائياً من Django Apps الموجودة
python manage.py sync_permissions
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import AppModule, Permission


class Command(BaseCommand):
    help = 'مزامنة الوحدات والصلاحيات تلقائياً من Django Apps'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-basic',
            action='store_true',
            help='إنشاء الصلاحيات الأساسية (view, add, edit, delete, manage) لكل وحدة'
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            self.stdout.write(self.style.WARNING('🔄 جاري مزامنة الوحدات والصلاحيات...'))
            
            # 1️⃣ تسجيل الوحدات
            modules = self.register_modules()
            
            # 2️⃣ إنشاء الصلاحيات الأساسية إذا طلب ذلك
            if options['create_basic']:
                self.create_basic_permissions(modules)
            
            self.stdout.write(self.style.SUCCESS('✅ تمت المزامنة بنجاح!'))

    def register_modules(self):
        """تسجيل جميع الوحدات من Django Apps"""
        self.stdout.write(self.style.HTTP_INFO('📦 تسجيل الوحدات...'))
        
        created_modules = AppModule.register_from_apps()
        
        if created_modules:
            for module in created_modules:
                self.stdout.write(f'  ✓ تم إنشاء وحدة: {module.name} ({module.code})')
            self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء {len(created_modules)} وحدة جديدة'))
        else:
            self.stdout.write(self.style.SUCCESS('✓ جميع الوحدات موجودة مسبقاً'))
        
        return AppModule.objects.filter(is_active=True)

    def create_basic_permissions(self, modules):
        """إنشاء الصلاحيات الأساسية لكل وحدة"""
        self.stdout.write(self.style.HTTP_INFO('🔐 إنشاء الصلاحيات الأساسية...'))
        
        total_created = 0
        for module in modules:
            created_perms = Permission.generate_for_module(module)
            if created_perms:
                for perm in created_perms:
                    self.stdout.write(f'  ✓ تم إنشاء: {perm.name} ({perm.code})')
                total_created += len(created_perms)
        
        if total_created > 0:
            self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء {total_created} صلاحية جديدة'))
        else:
            self.stdout.write(self.style.SUCCESS('✓ جميع الصلاحيات موجودة مسبقاً'))
