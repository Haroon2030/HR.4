"""نقل تلقائي: كل مستخدم بدور (specialist) → دور (hr_officer).

المنطق:
- قبل ترقية 0017، كان دور (specialist) يحمل اسم "أخصائي موارد بشرية"
- جميع المستخدمين الذين عُيّنوا له فعلياً قصدوا "أخصائي موارد بشرية"
- بعد 0017، الاسم انتقل إلى دور (hr_officer) — لكن المستخدمين بقوا
  مرتبطين بـ specialist (الذي صار "أخصائي إدخال البيانات")

نُصلح ذلك بنقلهم تلقائياً.

ذرّية: إذا لم يوجد دور hr_officer (تركيب جديد لا يحوي شيئاً)، يتجاوز.
"""
from django.db import migrations


def forward(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    UserProfile = apps.get_model('core', 'UserProfile')

    specialist = Role.objects.filter(role_type='specialist').first()
    hr_officer = Role.objects.filter(role_type='hr_officer').first()

    if not specialist or not hr_officer:
        return  # لا شيء للنقل

    moved = UserProfile.objects.filter(role=specialist).update(role=hr_officer)
    if moved:
        print(f"  → نُقل {moved} مستخدم من specialist إلى hr_officer")


def reverse(apps, schema_editor):
    # عكس آمن: لا نُرجع شيئاً تلقائياً (لا نعرف من كان أصلاً specialist)
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0017_swap_specialist_hr_officer_names'),
    ]
    operations = [migrations.RunPython(forward, reverse)]
