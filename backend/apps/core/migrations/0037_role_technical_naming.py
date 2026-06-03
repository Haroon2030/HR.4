"""تسمية تقنية موحّدة لأنواع الأدوار وأسماء الأدوار النظامية."""

from django.db import migrations, models

ROLE_TYPE_CHOICES = [
    ('admin', 'ADMIN — مدير النظام (صلاحيات كاملة)'),
    ('hr_manager', 'HR_MANAGER — مدير الموارد البشرية (المدير العام)'),
    ('hr_officer', 'HR_OFFICER — منفّذ عمليات الموارد البشرية'),
    ('admin_manager', 'ADMIN_MANAGER — مدير الإدارة (موافقة أولى)'),
    ('manager', 'BRANCH_MANAGER — مدير الفرع (موافقة أولى)'),
    ('specialist', 'DATA_SPECIALIST — أخصائي إدخال البيانات'),
    ('employee', 'EMPLOYEE — موظف (صلاحيات ذاتية)'),
]

SYSTEM_ROLES = {
    'admin': {
        'name': 'ADMIN — مدير النظام',
        'description': (
            'صلاحيات كاملة: مستخدمون، أدوار، إعدادات، فروع، موظفون، رواتب، تقارير، '
            'وجميع مراحل الموافقات.'
        ),
    },
    'hr_manager': {
        'name': 'HR_MANAGER — مدير الموارد البشرية',
        'description': (
            'إدارة شؤون الموظفين على مستوى الشركة، الرواتب، المستخدمون، التقارير الشاملة، '
            'والموافقة العامة (المرحلة الثانية) في دورة الطلبات.'
        ),
    },
    'hr_officer': {
        'name': 'HR_OFFICER — منفّذ الموارد البشرية',
        'description': (
            'تنفيذ المهام المُسندة بعد اعتماد المدير العام (المرحلة الأخيرة في دورة الموافقات).'
        ),
    },
    'admin_manager': {
        'name': 'ADMIN_MANAGER — مدير الإدارة',
        'description': (
            'الموافقة الأولى على طلبات موظفي الإدارة المعيّنة عليه '
            '(يُربط من التهيئة → الإدارات).'
        ),
    },
    'manager': {
        'name': 'BRANCH_MANAGER — مدير الفرع',
        'description': (
            'إدارة موظفي الفرع والموافقة الأولى على طلباتهم عند عدم وجود مدير إدارة فعّال.'
        ),
    },
    'specialist': {
        'name': 'DATA_SPECIALIST — أخصائي إدخال البيانات',
        'description': 'إدخال وتحديث بيانات الموظفين ضمن نطاق الفروع المعينة (بدون موافقات).',
    },
    'employee': {
        'name': 'EMPLOYEE — موظف',
        'description': 'عرض البيانات الشخصية وطلب الإجازات فقط.',
    },
}

CUSTOM_NAME_RENAMES = {
    'مدير المالية': 'FIN_MANAGER — مدير المالية',
    'المدير التقني': 'TECH_ADMIN — المدير التقني',
    'أخصائي موارد بشرية': 'HR_OFFICER — منفّذ الموارد البشرية',
    'الأدمن': 'ADMIN — مدير النظام',
    'مدير الموارد البشرية': 'HR_MANAGER — مدير الموارد البشرية',
    'الموارد البشرية': 'HR_MANAGER — مدير الموارد البشرية',
    'مدير فرع': 'BRANCH_MANAGER — مدير الفرع',
    'مدير إدارة': 'ADMIN_MANAGER — مدير الإدارة',
    'أخصائي إدخال البيانات': 'DATA_SPECIALIST — أخصائي إدخال البيانات',
    'موظف': 'EMPLOYEE — موظف',
}


def apply_technical_names(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    for role_type, meta in SYSTEM_ROLES.items():
        Role.objects.filter(role_type=role_type, is_system_role=True).update(
            name=meta['name'],
            description=meta['description'],
        )
        Role.objects.filter(role_type=role_type, is_system_role=False).update(
            description=meta['description'],
        )
    legacy_type_map = {
        'مدير المالية': 'manager',
        'المدير التقني': 'admin',
    }
    for old_name, new_name in CUSTOM_NAME_RENAMES.items():
        qs = Role.objects.filter(name=old_name).exclude(name=new_name)
        expected_type = legacy_type_map.get(old_name)
        if expected_type:
            qs = qs.filter(role_type=expected_type)
        for role in qs.only('id', 'name'):
            if Role.objects.filter(name=new_name).exclude(pk=role.pk).exists():
                continue
            role.name = new_name
            role.save(update_fields=['name'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0036_alter_role_type_labels'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicalrole',
            name='role_type',
            field=models.CharField(
                choices=ROLE_TYPE_CHOICES,
                default='employee',
                max_length=20,
                verbose_name='نوع الدور',
            ),
        ),
        migrations.AlterField(
            model_name='role',
            name='role_type',
            field=models.CharField(
                choices=ROLE_TYPE_CHOICES,
                default='employee',
                max_length=20,
                verbose_name='نوع الدور',
            ),
        ),
        migrations.RunPython(apply_technical_names, migrations.RunPython.noop),
    ]
