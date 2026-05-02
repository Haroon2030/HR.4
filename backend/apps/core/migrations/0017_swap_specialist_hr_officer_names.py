"""تصحيح الأسماء بحيث يحمل الدور الصحيح (hr_officer) اسم "أخصائي موارد بشرية".

المشكلة: الدور القديم (type=specialist) كان اسمه "أخصائي موارد بشرية" بعد ترقية 0016،
بينما الدور الجديد للدورة (type=hr_officer) اسمه "موظف موارد" — مما يجعل المستخدم
يختار الدور الخطأ من القائمة.

الحل:
  - specialist  → "أخصائي إدخال البيانات"  (تمييزه عن hr_officer)
  - hr_officer  → "أخصائي موارد بشرية"     (الاسم الواضح للدور النهائي)
"""
from django.db import migrations


SPECIALIST_NEW_NAME = 'أخصائي إدخال البيانات'
HR_OFFICER_NEW_NAME = 'أخصائي موارد بشرية'
TEMP_NAME = '__tmp_role_swap__'


def _rename(Role, role_type, new_name):
    qs = Role.objects.filter(role_type=role_type)
    if not qs.exists():
        return
    # نُحدّث جميع الأدوار من نفس النوع (عادةً واحد فقط)
    qs.update(name=new_name)


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')

    # 1) لكسر تعارض الاسم: انقل specialist إلى اسم مؤقت أولاً
    Role.objects.filter(role_type='specialist').update(name=TEMP_NAME)

    # 2) أعطِ hr_officer الاسم الواضح
    _rename(Role, 'hr_officer', HR_OFFICER_NEW_NAME)

    # 3) سمِّ specialist باسمه الجديد
    Role.objects.filter(name=TEMP_NAME).update(name=SPECIALIST_NEW_NAME)


def reverse(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Role.objects.filter(role_type='specialist').update(name=TEMP_NAME)
    Role.objects.filter(role_type='hr_officer').update(name='موظف موارد')
    Role.objects.filter(name=TEMP_NAME).update(name='أخصائي موارد بشرية')


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_rename_roles'),
    ]
    operations = [migrations.RunPython(forward, reverse)]
