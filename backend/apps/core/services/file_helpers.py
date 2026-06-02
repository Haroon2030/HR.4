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


def _build_renamed_storage_name(old_storage_name: str, new_basename: str) -> str | None:
    """يُرجع المسار الجديد في التخزين أو None إن لم يتغيّر الاسم."""
    ext = os.path.splitext(old_storage_name)[1]
    cleaned = _safe_filename(new_basename)
    if not cleaned:
        return None
    if not cleaned.lower().endswith(ext.lower()):
        cleaned = f'{cleaned}{ext}'
    new_name = os.path.join(os.path.dirname(old_storage_name), cleaned)
    if new_name.replace('\\', '/') == old_storage_name.replace('\\', '/'):
        return None
    return new_name


def rename_stored_file_field(file_field, new_basename: str) -> bool:
    """إعادة تسمية ملف محفوظ مسبقاً (بدون رفع جديد)."""
    if not file_field or not file_field.name:
        return False
    new_name = _build_renamed_storage_name(file_field.name, new_basename)
    if not new_name:
        return False
    storage = file_field.storage
    old_name = file_field.name
    if not storage.exists(old_name):
        return False
    with storage.open(old_name, 'rb') as content:
        storage.save(new_name, content)
    if storage.exists(old_name):
        storage.delete(old_name)
    file_field.name = new_name
    return True


def apply_stored_file_rename(instance, request, field_name: str) -> bool:
    """إعادة تسمية ملف موجود إذا أُرسل <field>__rename بدون رفع ملف جديد."""
    if request.FILES.get(field_name):
        return False
    rename_val = (request.POST.get(f'{field_name}__rename') or '').strip()
    if not rename_val:
        return False
    return rename_stored_file_field(getattr(instance, field_name), rename_val)


EMPLOYEE_DOCUMENT_FIELD_NAMES = (
    'commencement_document',
    'id_document',
    'passport_document',
    'contract_document',
    'other_documents',
)


def apply_employee_document_renames(instance, request) -> list[str]:
    """تطبيق إعادة تسمية مستندات الموظف المحفوظة. يُرجع أسماء الحقول المُحدَّثة."""
    updated: list[str] = []
    for field_name in EMPLOYEE_DOCUMENT_FIELD_NAMES:
        if apply_stored_file_rename(instance, request, field_name):
            updated.append(field_name)
    return updated
