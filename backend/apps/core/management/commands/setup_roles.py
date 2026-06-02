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
            # 2️⃣ مدير فرع — الموافقة الأولى على طلبات فرعه
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'مدير فرع',
                'role_type': Role.RoleType.MANAGER,
                'description': 'الموافقة الأولى في دورة الطلبات (مرحلة مدير الفرع). يدير موظفي فرعه ويراجع طلبات الإجازات والنقل والرواتب.',
                'is_system_role': True,
                'permissions': [
                    # الموظفين
                    'employees.view',
                    'employees.add',
                    'employees.edit',
                    # الأقسام والفروع
                    'departments.view',
                    'branches.view',
                    # الإجازات (أكواد legacy — التنفيذ الفعلي عبر employees.edit)
                    'leaves.view',
                    'leaves.approve',
                    'leaves.manage',
                    # التقارير
                    'reports.view',
                    'operations.view',
                    'operations.approve_branch',
                    'operations.return',
                ],
            },

            # ═══════════════════════════════════════════════════════════
            # 2b مدير إدارة — الموافقة الأولى لموظفي إدارته
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'مدير إدارة',
                'role_type': Role.RoleType.ADMIN_MANAGER,
                'description': (
                    'الموافقة الأولى على طلبات موظفي الإدارة المعيّنة عليه. '
                    'يُعيَّن أيضاً كـ «مدير الإدارة» من التهيئة → الإدارات.'
                ),
                'is_system_role': True,
                'permissions': [
                    'employees.view',
                    'employees.add',
                    'employees.edit',
                    'departments.view',
                    'branches.view',
                    'leaves.view',
                    'leaves.approve',
                    'leaves.manage',
                    'reports.view',
                    'operations.view',
                    'operations.approve_admin',
                    'operations.return',
                ],
            },
            
            # ═══════════════════════════════════════════════════════════
            # 3️⃣ مدير الموارد البشرية (المدير العام في دورة الموافقات)
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'مدير الموارد البشرية',
                'role_type': Role.RoleType.HR_MANAGER,
                'description': 'الموافقة الثانية (المدير العام) في دورة الطلبات. يوافق على ما اعتمده مدير الفرع ويُسند المهمة لموظف موارد للتنفيذ.',
                'is_system_role': True,
                'permissions': [
                    # الموظفين - كل الصلاحيات
                    'employees.view',
                    'employees.add',
                    'employees.edit',
                    'employees.delete',
                    # الأقسام - كل الصلاحيات
                    'departments.view',
                    'departments.add',
                    'departments.edit',
                    'departments.delete',
                    'departments.manage',
                    # الإجازات (أكواد legacy)
                    'leaves.view',
                    'leaves.approve',
                    'leaves.manage',
                    # الرواتب
                    'payroll.view',
                    'payroll.manage',
                    'payroll.process',
                    'payroll.view_reports',
                    # المستخدمين - عرض وإضافة وتعديل
                    'users.view',
                    'users.add',
                    'users.edit',
                    # التقارير - عرض
                    'reports.view',
                    'operations.view',
                    'operations.approve_branch',
                    'operations.approve_admin',
                    'operations.approve_gm',
                    'operations.approve_officer',
                    'operations.return',
                    'operations.resubmit',
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
                    'leaves.request',    # طلب إجازة (يتوافق مع setup_permissions_and_roles)
                ],
            },

            # ═══════════════════════════════════════════════════════════
            # 5️⃣ أخصائي موارد بشرية (المرحلة الأخيرة في دورة الموافقات)
            # ═══════════════════════════════════════════════════════════
            {
                'name': 'أخصائي موارد بشرية',
                'role_type': Role.RoleType.HR_OFFICER,
                'description': 'يستلم المهام المُسندة من المدير العام وينفّذها بعد موافقته (المرحلة الأخيرة في دورة الموافقات).',
                'is_system_role': True,
                'permissions': [
                    'employees.view',
                    'employees.edit',
                    'leaves.view',
                    'leaves.manage',
                    'operations.view',
                    'operations.approve_officer',
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
