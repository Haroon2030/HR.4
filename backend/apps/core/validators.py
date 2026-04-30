"""Validators مشتركة للحقول."""
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

# الحد الأقصى لحجم الملف (10MB)
MAX_UPLOAD_SIZE_MB = 10
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# الامتدادات المسموحة للمستندات
ALLOWED_DOCUMENT_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'doc', 'docx']

document_extension_validator = FileExtensionValidator(
    allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS,
    message=f'صيغة الملف غير مدعومة. الصيغ المسموحة: {", ".join(ALLOWED_DOCUMENT_EXTENSIONS)}',
)


def validate_file_size(file):
    """تحقق من أن حجم الملف ضمن الحد المسموح.

    يُطبَّق فقط على الملفات المرفوعة حديثاً (UploadedFile). الملفات
    المخزّنة مسبقاً (FieldFile مع _committed=True) تُتجاهَل لأن
    الوصول إلى .size سيستدعي HeadObject على المخزِّن البعيد ويفشل
    إذا كان الملف غير موجود (مثل ملفات قديمة كانت محلية قبل R2).
    """
    if not file:
        return
    # تجاهل الملفات المخزّنة مسبقاً ولم تُستبدل بملف جديد
    if getattr(file, '_committed', True):
        return
    try:
        size = file.size
    except Exception:
        return
    if size > MAX_UPLOAD_SIZE:
        raise ValidationError(
            f'حجم الملف ({size / (1024*1024):.1f}MB) يتجاوز الحد المسموح ({MAX_UPLOAD_SIZE_MB}MB).'
        )


# قائمة validators جاهزة للاستخدام في FileField
DOCUMENT_VALIDATORS = [document_extension_validator, validate_file_size]
