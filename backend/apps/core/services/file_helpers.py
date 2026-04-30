"""أدوات مساعدة للملفات المرفوعة (إعادة التسمية الآمنة)."""
import os
import re
import unicodedata


def _safe_filename(raw: str) -> str:
    """ينظّف اسم الملف: يُبقي الحروف العربية والإنجليزية والأرقام والشرطات."""
    if not raw:
        return ''
    # إزالة المسارات والامتدادات الخطرة
    raw = os.path.basename(raw).strip()
    raw = unicodedata.normalize('NFKC', raw)
    # استبدال الفراغات والرموز غير المرغوبة بـ _
    raw = re.sub(r'[\\/:*?"<>|]+', '_', raw)
    raw = re.sub(r'\s+', '_', raw)
    raw = raw.strip('._- ')
    return raw[:120]  # حدّ معقول للطول


def apply_uploaded_file_rename(request, field_name: str):
    """
    يُعيد تسمية الملف المرفوع في request.FILES[field_name] إذا كان المستخدم
    أرسل اسماً جديداً في حقل "<field_name>__rename".

    يحفظ الامتداد الأصلي ويرجع كائن الملف نفسه (مع تعديل اسمه)، أو None إن لم يوجد ملف.
    """
    f = request.FILES.get(field_name)
    if not f:
        return None
    new_name = (request.POST.get(f'{field_name}__rename') or '').strip()
    if not new_name:
        return f
    ext = os.path.splitext(f.name)[1]
    cleaned = _safe_filename(new_name)
    if not cleaned:
        return f
    # إذا تضمّن المستخدم الامتداد، لا نُكرّره
    if not cleaned.lower().endswith(ext.lower()):
        cleaned = f'{cleaned}{ext}'
    f.name = cleaned
    return f
