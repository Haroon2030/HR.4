"""ضمان وجود دور (hr_officer) في قاعدة البيانات.

في بعض بيئات الإنتاج التي رُكّبت قبل إضافة hr_officer إلى choices لم يُنشأ
الدور أبداً (`setup_roles` كان معطّلاً، و data_dump.json لا يحويه).

النتيجة: ترقيتا 0017 و 0018 تخطّتا بصمت لأنهما تتحققان من وجود الدور أولاً.

هذه الترقية:
1. تُنشئ دور hr_officer إن لم يكن موجوداً.
2. تُعيد تطبيق منطق 0017: تأكُّد من اسمه "أخصائي موارد بشرية"
   و specialist باسم "أخصائي إدخال البيانات".
3. تُعيد تطبيق منطق 0018: نقل أي مستخدم من specialist إلى hr_officer
   (لأنه قبل ذلك كان specialist يحمل اسم "أخصائي موارد بشرية").

ذرّية وآمنة عند التكرار.
"""
from django.db import migrations


HR_OFFICER_NAME = 'أخصائي موارد بشرية'
SPECIALIST_NAME = 'أخصائي إدخال البيانات'
TEMP_NAME = '__tmp_role_swap_v2__'


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    UserProfile = apps.get_model('core', 'UserProfile')

    # ─── 1) ضمان وجود الدورين ──────────────────────────────────────────
    hr_officer = Role.objects.filter(role_type='hr_officer').first()
    specialist = Role.objects.filter(role_type='specialist').first()

    if not hr_officer:
        hr_officer = Role.objects.create(
            name=HR_OFFICER_NAME,
            role_type='hr_officer',
            description='يستلم المهام المُسندة من مدير الموارد البشرية وينفّذها بعد موافقته (المرحلة الأخيرة في دورة الموافقات).',
            is_system_role=True,
            is_active=True,
        )
        print(f"  → أُنشئ دور 'أخصائي موارد بشرية' (id={hr_officer.id})")
    else:
        # تأكّد من تفعيله
        Role.objects.filter(pk=hr_officer.pk).update(is_active=True)

    # ─── 2) تصحيح الأسماء (مع تجنّب تعارض UNIQUE إن وُجد) ───────────────
    if specialist:
        # انقل specialist إلى اسم مؤقت لتحرير الأسماء
        Role.objects.filter(pk=specialist.pk).update(name=TEMP_NAME)

    # تأكّد من اسم hr_officer
    Role.objects.filter(pk=hr_officer.pk).update(name=HR_OFFICER_NAME)

    # أعطِ specialist اسمه الجديد
    if specialist:
        Role.objects.filter(name=TEMP_NAME).update(name=SPECIALIST_NAME)

    # ─── 3) نقل المستخدمين من specialist إلى hr_officer ────────────────
    if specialist:
        moved = UserProfile.objects.filter(role_id=specialist.pk).update(
            role_id=hr_officer.pk
        )
        if moved:
            print(f"  → نُقل {moved} مستخدم من specialist إلى hr_officer")


def reverse(apps, schema_editor):
    pass  # عكس آمن: لا نلمس شيئاً


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0018_migrate_specialists_to_hr_officer'),
    ]
    operations = [migrations.RunPython(forward, reverse)]
