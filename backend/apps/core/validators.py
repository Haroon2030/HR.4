"""Validators مشتركة للحقول."""
import os

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

# الحد الأقصى لحجم الملف — يُوافق DATA_UPLOAD_MAX_MEMORY_SIZE في settings
MAX_UPLOAD_SIZE_MB = 10
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# الامتدادات المسموحة للمستندات
ALLOWED_DOCUMENT_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'doc', 'docx']

document_extension_validator = FileExtensionValidator(
    allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS,
    message=f'صيغة الملف غير مدعومة. الصيغ المسموحة: {", ".join(ALLOWED_DOCUMENT_EXTENSIONS)}',
)


def _read_upload_header(file, length: int = 16) -> bytes:
    position = file.tell() if hasattr(file, 'tell') else None
    try:
        if hasattr(file, 'seek'):
            file.seek(0)
        header = file.read(length)
        if not isinstance(header, bytes):
            header = bytes(header or b'')
        return header
    finally:
        if hasattr(file, 'seek') and position is not None:
            file.seek(position)


def _extension_matches_magic(ext: str, header: bytes) -> bool:
    ext = (ext or '').lower().lstrip('.')
    if ext == 'pdf':
        return header.startswith(b'%PDF')
    if ext in ('jpg', 'jpeg'):
        return header.startswith(b'\xff\xd8\xff')
    if ext == 'png':
        return header.startswith(b'\x89PNG\r\n\x1a\n')
    if ext == 'gif':
        return header[:6] in (b'GIF87a', b'GIF89a')
    if ext == 'webp':
        return len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP'
    if ext == 'doc':
        return header.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
    if ext == 'docx':
        return header.startswith(b'PK\x03\x04')
    return False


def validate_upload_magic_bytes(file):
    """يتأكد أن بداية الملف تطابق الامتداد (يقلّل رفع ملفات خبيثة بامتداد مزيف)."""
    if not file or getattr(file, '_committed', True):
        return
    name = getattr(file, 'name', '') or ''
    ext = os.path.splitext(name)[1].lstrip('.').lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS and ext not in ALLOWED_IMAGE_EXTENSIONS:
        return
    try:
        header = _read_upload_header(file)
    except Exception:
        return
    if not header:
        raise ValidationError('الملف فارغ أو غير قابل للقراءة.')
    if not _extension_matches_magic(ext, header):
        raise ValidationError('محتوى الملف لا يطابق صيغة الامتداد المرفوع.')


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
DOCUMENT_VALIDATORS = [
    document_extension_validator,
    validate_file_size,
    validate_upload_magic_bytes,
]


# ─── الصور (Images) ───────────────────────────────────────────────────
ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp', 'gif']

image_extension_validator = FileExtensionValidator(
    allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
    message=f'صيغة الصورة غير مدعومة. الصيغ المسموحة: {", ".join(ALLOWED_IMAGE_EXTENSIONS)}',
)

# الحد الأقصى للصور (5MB)
MAX_IMAGE_SIZE_MB = 5
MAX_IMAGE_SIZE = MAX_IMAGE_SIZE_MB * 1024 * 1024


def validate_image_size(file):
    """تحقق من حجم الصور المرفوعة (5MB)."""
    if not file:
        return
    if getattr(file, '_committed', True):
        return
    try:
        size = file.size
    except Exception:
        return
    if size > MAX_IMAGE_SIZE:
        raise ValidationError(
            f'حجم الصورة ({size / (1024*1024):.1f}MB) يتجاوز الحد المسموح ({MAX_IMAGE_SIZE_MB}MB).'
        )


IMAGE_VALIDATORS = [
    image_extension_validator,
    validate_image_size,
    validate_upload_magic_bytes,
]
