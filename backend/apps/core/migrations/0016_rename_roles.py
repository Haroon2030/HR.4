"""
إعادة تسمية الأدوار لتعكس دورة الموافقات متعدّدة المراحل.
- مدير فرع او ادارة موظف → مدير فرع
- الموارد البشرية         → مدير الموارد البشرية
- أخصائي موارد مشتريات    → أخصائي موارد بشرية
"""
from django.db import migrations


RENAMES = {
    'مدير فرع او ادارة موظف': (
        'مدير فرع',
        'الموافقة الأولى في دورة الطلبات (مرحلة مدير الفرع). '
        'يدير موظفي فرعه ويراجع طلبات الإجازات والنقل والرواتب.',
    ),
    'الموارد البشرية': (
        'مدير الموارد البشرية',
        'الموافقة الثانية (المدير العام) في دورة الطلبات. '
        'يوافق على ما اعتمده مدير الفرع ويُسند المهمة لموظف موارد للتنفيذ.',
    ),
    'أخصائي موارد مشتريات': (
        'أخصائي موارد بشرية',
        'يُنشئ طلبات العمليات (إجازات، نقل، تعديل راتب، إنهاء خدمة، إعادة تفعيل) '
        'لإرسالها لدورة الموافقات.',
    ),
}

REVERSE = {new: (old, '') for old, (new, _) in RENAMES.items()}


def rename_forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    for old, (new, desc) in RENAMES.items():
        # تجنّب الاصطدام: لو الاسم الجديد موجود مسبقاً، تخطَّ
        if Role.objects.filter(name=new).exists():
            continue
        updated = Role.objects.filter(name=old).update(name=new, description=desc)
        if updated:
            print(f'  ✓ renamed role: {old} -> {new}')


def rename_reverse(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    for new, (old, _) in REVERSE.items():
        if Role.objects.filter(name=old).exists():
            continue
        Role.objects.filter(name=new).update(name=old)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_migrate_pending_action_statuses'),
    ]

    operations = [
        migrations.RunPython(rename_forward, rename_reverse),
    ]
