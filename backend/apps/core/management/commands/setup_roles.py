"""
إعداد الأدوار الأساسية الأربعة بعد مزامنة الصلاحيات
python manage.py setup_roles
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Role, Permission


class Command(BaseCommand):
    help = 'إنشاء الأدوار الأساسية الأربعة في النظام'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='إعادة إنشاء الأدوار (سيحذف ويعيد إنشاء الأدوار النظامية)'
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            self.stdout.write(self.style.WARNING('👥 جاري إعداد الأدوار...'))
            
            if options['reset']:
                self.stdout.write(self.style.WARNING('⚠️  إعادة تعيين الأدوار النظامية...'))
                # استخدام hard_delete بدلاً من soft delete
                system_roles = Role.all_objects.filter(is_system_role=True)
                for role in system_roles:
                    role.hard_delete()
            
            self.create_roles()
            
            self.stdout.write(self.style.SUCCESS('✅ تم إعداد الأدوار بنجاح!'))

    def create_roles(self):
        """إنشاء الأدوار الأربعة مع صلاحياتها"""
        self.stdout.write(self.style.HTTP_INFO('👥 إنشاء/تحديث الأدوار...'))
        
        # الحصول على جميع الصلاحيات مصنفة حسب الكود
        all_permissions = {p.code: p for p in Permission.objects.select_related('module').all()}
        
        roles_config = [
            # ═══════════════════════════════════════════════════════════
            # 1️⃣ الأدمن (كل الصلاحيات)
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'الأدمن',
                'role_type': Role.RoleType.ADMIN,
                'description': 'صلاحيات كاملة على جميع أجزاء النظام. يمكنه إدارة المستخدمين والإعدادات وجميع البيانات.',
                'is_system_role': True,
                'permissions': 'all',  # كل الصلاحيات
            },
            
            # ═══════════════════════════════════════════════════════════
            # 2️⃣ مدير فرع أو إدارة موظف
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'مدير فرع او ادارة موظف',
                'role_type': Role.RoleType.MANAGER,
                'description': 'يمكنه عرض وإدارة موظفي فرعه/قسمه، والموافقة على الإجازات والحضور.',
                'is_system_role': True,
                'permissions': [
                    # الموظفين
                    'employees.view',
                    'employees.add',
                    'employees.edit',
                    # الأقسام والفروع
                    'departments.view',
                    # الحضور
                    'attendance.view',
                    'attendance.manage',
                    'attendance.approve',
                    # الإجازات
                    'leaves.view',
                    'leaves.approve',
                    'leaves.manage',
                    # التقارير
                    'reports.view',
                ],
            },
            
            # ═══════════════════════════════════════════════════════════
            # 3️⃣ الموارد البشرية
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'الموارد البشرية',
                'role_type': Role.RoleType.HR_MANAGER,
                'description': 'صلاحيات إدارة شؤون الموظفين، الرواتب، الحضور، والإجازات.',
                'is_system_role': True,
                'permissions': [
                    # الموظفين - كل الصلاحيات
                    'employees.view',
                    'employees.add',
                    'employees.edit',
                    'employees.delete',
                    'employees.manage',
                    # الأقسام - كل الصلاحيات
                    'departments.view',
                    'departments.add',
                    'departments.edit',
                    'departments.delete',
                    'departments.manage',
                    # الحضور - كل الصلاحيات
                    'attendance.view',
                    'attendance.add',
                    'attendance.edit',
                    'attendance.delete',
                    'attendance.manage',
                    'attendance.approve',
                    # الإجازات - كل الصلاحيات
                    'leaves.view',
                    'leaves.add',
                    'leaves.edit',
                    'leaves.delete',
                    'leaves.approve',
                    'leaves.manage',
                    # الرواتب - كل الصلاحيات
                    'payroll.view',
                    'payroll.add',
                    'payroll.edit',
                    'payroll.delete',
                    'payroll.manage',
                    # المستخدمين - عرض وإضافة وتعديل
                    'users.view',
                    'users.add',
                    'users.edit',
                    # التقارير - عرض
                    'reports.view',
                ],
            },
            
            # ═══════════════════════════════════════════════════════════
            # 4️⃣ موظف عادي
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'موظف',
                'role_type': Role.RoleType.EMPLOYEE,
                'description': 'موظف عادي يمكنه فقط عرض بياناته الشخصية وطلب الإجازات.',
                'is_system_role': True,
                'permissions': [
                    # عرض بياناته فقط
                    'employees.view',  # (سيتم تطبيق فلتر لرؤية نفسه فقط في الـ views)
                    # الإجازات
                    'leaves.view',  # (يرى إجازاته فقط)
                    'leaves.add',    # طلب إجازة
                    # الحضور
                    'attendance.view',  # (يرى حضوره فقط)
                ],
            },
        ]
        
        for role_config in roles_config:
            # إنشاء أو تحديث الدور
            role, created = Role.objects.update_or_create(
                role_type=role_config['role_type'],
                defaults={
                    'name': role_config['name'],
                    'description': role_config['description'],
                    'is_system_role': role_config['is_system_role'],
                    'is_active': True,
                }
            )
            
            # ربط الصلاحيات
            if role_config['permissions'] == 'all':
                role.permissions.set(all_permissions.values())
                perm_count = len(all_permissions)
            else:
                role_permissions = [all_permissions[code] for code in role_config['permissions'] if code in all_permissions]
                role.permissions.set(role_permissions)
                perm_count = len(role_permissions)
            
            action = 'إنشاء' if created else 'تحديث'
            self.stdout.write(
                self.style.SUCCESS(
                    f'  ✓ تم {action} الدور: {role.name} ({perm_count} صلاحية)'
                )
            )
        
        self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء/تحديث {len(roles_config)} دور'))
