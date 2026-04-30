"""
إعداد نظام الصلاحيات والأدوار الكامل
python manage.py setup_permissions_and_roles
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Role, Permission


class Command(BaseCommand):
    help = 'إنشاء الصلاحيات والأدوار الأساسية الأربعة في النظام'

    def handle(self, *args, **options):
        with transaction.atomic():
            self.stdout.write(self.style.WARNING('🔧 جاري إعداد الصلاحيات والأدوار...'))
            
            # 1️⃣ إنشاء الصلاحيات
            permissions = self.create_permissions()
            
            # 2️⃣ إنشاء الأدوار الأربعة
            self.create_roles(permissions)
            
            self.stdout.write(self.style.SUCCESS('✅ تم إعداد نظام الصلاحيات والأدوار بنجاح!'))

    def create_permissions(self):
        """إنشاء جميع الصلاحيات في النظام"""
        self.stdout.write(self.style.HTTP_INFO('📋 إنشاء الصلاحيات...'))
        
        permissions_data = [
            # ═══════════════════════════════════════════════════════════
            # الموظفين (Employees)
            # ═══════════════════════════════════════════════════════════
            {'code': 'employees.view', 'name': 'عرض الموظفين', 'module': 'employees'},
            {'code': 'employees.add', 'name': 'إضافة موظف', 'module': 'employees'},
            {'code': 'employees.edit', 'name': 'تعديل موظف', 'module': 'employees'},
            {'code': 'employees.delete', 'name': 'حذف موظف', 'module': 'employees'},
            {'code': 'employees.view_salary', 'name': 'عرض رواتب الموظفين', 'module': 'employees'},
            {'code': 'employees.edit_salary', 'name': 'تعديل رواتب الموظفين', 'module': 'employees'},
            
            # ═══════════════════════════════════════════════════════════
            # الأقسام والفروع (Departments & Branches)
            # ═══════════════════════════════════════════════════════════
            {'code': 'departments.view', 'name': 'عرض الأقسام', 'module': 'departments'},
            {'code': 'departments.manage', 'name': 'إدارة الأقسام', 'module': 'departments'},
            {'code': 'branches.view', 'name': 'عرض الفروع', 'module': 'departments'},
            {'code': 'branches.manage', 'name': 'إدارة الفروع', 'module': 'departments'},
            
            # ═══════════════════════════════════════════════════════════
            # الحضور والغياب (Attendance)
            # ═══════════════════════════════════════════════════════════
            {'code': 'attendance.view', 'name': 'عرض الحضور والغياب', 'module': 'attendance'},
            {'code': 'attendance.manage', 'name': 'إدارة الحضور والغياب', 'module': 'attendance'},
            {'code': 'attendance.approve', 'name': 'الموافقة على التعديلات', 'module': 'attendance'},
            
            # ═══════════════════════════════════════════════════════════
            # الإجازات (Leaves)
            # ═══════════════════════════════════════════════════════════
            {'code': 'leaves.view', 'name': 'عرض الإجازات', 'module': 'leaves'},
            {'code': 'leaves.request', 'name': 'طلب إجازة', 'module': 'leaves'},
            {'code': 'leaves.approve', 'name': 'الموافقة على الإجازات', 'module': 'leaves'},
            {'code': 'leaves.manage', 'name': 'إدارة الإجازات', 'module': 'leaves'},
            
            # ═══════════════════════════════════════════════════════════
            # الرواتب (Payroll)
            # ═══════════════════════════════════════════════════════════
            {'code': 'payroll.view', 'name': 'عرض الرواتب', 'module': 'payroll'},
            {'code': 'payroll.manage', 'name': 'إدارة الرواتب', 'module': 'payroll'},
            {'code': 'payroll.process', 'name': 'معالجة الرواتب', 'module': 'payroll'},
            {'code': 'payroll.view_reports', 'name': 'عرض تقارير الرواتب', 'module': 'payroll'},
            
            # ═══════════════════════════════════════════════════════════
            # المستخدمين (Users)
            # ═══════════════════════════════════════════════════════════
            {'code': 'users.view', 'name': 'عرض المستخدمين', 'module': 'users'},
            {'code': 'users.add', 'name': 'إضافة مستخدم', 'module': 'users'},
            {'code': 'users.edit', 'name': 'تعديل مستخدم', 'module': 'users'},
            {'code': 'users.delete', 'name': 'حذف مستخدم', 'module': 'users'},
            {'code': 'users.manage_roles', 'name': 'إدارة الأدوار', 'module': 'users'},
            
            # ═══════════════════════════════════════════════════════════
            # التقارير (Reports)
            # ═══════════════════════════════════════════════════════════
            {'code': 'reports.view', 'name': 'عرض التقارير', 'module': 'reports'},
            {'code': 'reports.view_all', 'name': 'عرض جميع التقارير', 'module': 'reports'},
            {'code': 'reports.export', 'name': 'تصدير التقارير', 'module': 'reports'},
            
            # ═══════════════════════════════════════════════════════════
            # الإعدادات (Settings)
            # ═══════════════════════════════════════════════════════════
            {'code': 'settings.view', 'name': 'عرض الإعدادات', 'module': 'settings'},
            {'code': 'settings.manage', 'name': 'إدارة الإعدادات', 'module': 'settings'},
        ]
        
        created_permissions = {}
        for perm_data in permissions_data:
            perm, created = Permission.objects.get_or_create(
                code=perm_data['code'],
                defaults={
                    'name': perm_data['name'],
                    'module': perm_data['module'],
                    'is_active': True,
                }
            )
            if created:
                self.stdout.write(f'  ✓ تم إنشاء: {perm.name}')
            created_permissions[perm.code] = perm
        
        self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء {len(created_permissions)} صلاحية'))
        return created_permissions

    def create_roles(self, permissions):
        """إنشاء الأدوار الأربعة مع صلاحياتها"""
        self.stdout.write(self.style.HTTP_INFO('👥 إنشاء الأدوار...'))
        
        roles_config = [
            # ═══════════════════════════════════════════════════════════
            # 1️⃣ الأدمن (كل الصلاحيات)
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'الأدمن',
                'role_type': Role.RoleType.ADMIN,
                'description': 'صلاحيات كاملة على جميع أجزاء النظام. يمكنه إدارة المستخدمين والإعدادات وجميع البيانات.',
                'is_system_role': True,
                'permissions': list(permissions.keys()),  # كل الصلاحيات
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
                    'employees.view_salary',
                    # الأقسام والفروع
                    'departments.view',
                    'branches.view',
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
                    'reports.export',
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
                    # الموظفين
                    'employees.view',
                    'employees.add',
                    'employees.edit',
                    'employees.delete',
                    'employees.view_salary',
                    'employees.edit_salary',
                    # الأقسام والفروع
                    'departments.view',
                    'departments.manage',
                    'branches.view',
                    'branches.manage',
                    # الحضور
                    'attendance.view',
                    'attendance.manage',
                    'attendance.approve',
                    # الإجازات
                    'leaves.view',
                    'leaves.approve',
                    'leaves.manage',
                    # الرواتب
                    'payroll.view',
                    'payroll.manage',
                    'payroll.process',
                    'payroll.view_reports',
                    # المستخدمين
                    'users.view',
                    'users.add',
                    'users.edit',
                    # التقارير
                    'reports.view',
                    'reports.view_all',
                    'reports.export',
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
                    # طلب إجازة
                    'leaves.request',
                    'leaves.view',  # (يرى إجازاته فقط)
                    # عرض حضوره
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
            role_permissions = [permissions[code] for code in role_config['permissions'] if code in permissions]
            role.permissions.set(role_permissions)
            
            action = 'إنشاء' if created else 'تحديث'
            self.stdout.write(
                self.style.SUCCESS(
                    f'  ✓ تم {action} الدور: {role.name} ({len(role_permissions)} صلاحية)'
                )
            )
        
        self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء/تحديث {len(roles_config)} دور'))
