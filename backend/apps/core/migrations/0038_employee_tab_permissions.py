"""إنشاء صلاحيات تبويبات ملف الموظف ومنحها للأدوار التي تملك employees.view."""

from django.db import migrations

TAB_KEYS = (
    'main', 'salary', 'leaves', 'schedule', 'warnings', 'custodies', 'trips',
    'contract', 'loans', 'absences', 'fingerprint', 'docs', 'accruals', 'archive',
    'termination',
)

TAB_LABELS = {
    'main': 'بيانات الموظف',
    'salary': 'الراتب',
    'leaves': 'الإجازات',
    'schedule': 'الجدول',
    'warnings': 'الإفادات والإنذارات',
    'custodies': 'العهد',
    'trips': 'رحلات العمل',
    'contract': 'العقد',
    'loans': 'السلف',
    'absences': 'الغيابات',
    'fingerprint': 'البصمة',
    'docs': 'المستندات',
    'accruals': 'المخصصات والأرصدة',
    'archive': 'أرشيف الحركة',
    'termination': 'التصفيات',
}


def forward(apps, schema_editor):
    AppModule = apps.get_model('core', 'AppModule')
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')

    tab_perm_ids = []
    for idx, key in enumerate(TAB_KEYS):
        module_code = f'employee_tab_{key}'
        module, _ = AppModule.objects.update_or_create(
            code=module_code,
            defaults={
                'name': f'تبويب — {TAB_LABELS[key]}',
                'icon': 'layout-grid',
                'order': 131 + idx,
                'is_active': True,
            },
        )
        perm, _ = Permission.objects.update_or_create(
            code=f'{module_code}.view',
            defaults={
                'module': module,
                'operation': 'view',
                'name': f'عرض تبويب — {TAB_LABELS[key]}',
                'is_active': True,
            },
        )
        tab_perm_ids.append(perm.id)

    emp_view = Permission.objects.filter(code='employees.view', is_active=True).first()
    if not emp_view:
        return

    for role in Role.objects.filter(permissions=emp_view).distinct():
        role.permissions.add(*tab_perm_ids)

    for role in Role.objects.filter(role_type='admin', is_active=True):
        role.permissions.add(*Permission.objects.filter(id__in=tab_perm_ids))


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_role_technical_naming'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
