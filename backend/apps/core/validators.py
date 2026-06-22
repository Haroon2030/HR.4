"""Validators مشتركة للحقول."""
import io
import os
import zipfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import FileExtensionValidator

# الحد الأقصى لحجم الملف — يُوافق DATA_UPLOAD_MAX_MEMORY_SIZE في settings
MAX_UPLOAD_SIZE_MB = 10
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# الامتدادات المسموحة لمرفقات الموظفين والطلبات
ALLOWED_DOCUMENT_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'xlsx']
EMPLOYEE_UPLOAD_ACCEPT = '.pdf,.jpg,.jpeg,.png,.xlsx'
ALLOWED_DOCUMENT_EXTENSIONS_LABEL = 'pdf, jpg, png, xlsx'

document_extension_validator = FileExtensionValidator(
    allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS,
    message=(
        f'صيغة الملف غير مدعومة. الصيغ المسموحة: {ALLOWED_DOCUMENT_EXTENSIONS_LABEL}'
    ),
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


def _read_upload_bytes(file) -> bytes:
    position = file.tell() if hasattr(file, 'tell') else None
    try:
        if hasattr(file, 'seek'):
            file.seek(0)
        data = file.read()
        return data if isinstance(data, bytes) else bytes(data or b'')
    finally:
        if hasattr(file, 'seek') and position is not None:
            file.seek(position)


def _is_xlsx_archive(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return any(name.startswith('xl/') for name in archive.namelist())
    except zipfile.BadZipFile:
        return False


def _extension_matches_magic(ext: str, header: bytes, file=None) -> bool:
    ext = (ext or '').lower().lstrip('.')
    if ext == 'pdf':
        return header.startswith(b'%PDF')
    if ext in ('jpg', 'jpeg'):
        return header.startswith(b'\xff\xd8\xff')
    if ext == 'png':
        return header.startswith(b'\x89PNG\r\n\x1a\n')
    if ext == 'xlsx':
        if not header.startswith(b'PK\x03\x04'):
            return False
        if file is None:
            return True
        return _is_xlsx_archive(_read_upload_bytes(file))
    return False


def _is_new_upload(file) -> bool:
    """ملف مرفوع حديثاً — وليس ملفاً مخزّناً مسبقاً في التخزين."""
    if not file:
        return False
    if getattr(file, '_committed', None) is False:
        return True
    return isinstance(file, UploadedFile)


def validate_upload_magic_bytes(file):
    """يتأكد أن بداية الملف تطابق الامتداد (يقلّل رفع ملفات خبيثة بامتداد مزيف)."""
    if not file or not _is_new_upload(file):
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
    if not _extension_matches_magic(ext, header, file=file):
        raise ValidationError('محتوى الملف لا يطابق صيغة الامتداد المرفوع.')


def validate_file_size(file):
    """تحقق من أن حجم الملف ضمن الحد المسموح.

    يُطبَّق فقط على الملفات المرفوعة حديثاً (UploadedFile). الملفات
    المخزّنة مسبقاً (FieldFile مع _committed=True) تُتجاهَل لأن
    الوصول إلى .size سيستدعي HeadObject على المخزِّن البعيد ويفشل
    إذا كان الملف غير موجود (مثل ملفات قديمة كانت محلية قبل R2).
    """
    if not file or not _is_new_upload(file):
        return
    try:
        size = file.size
    except Exception:
        return
    if size > MAX_UPLOAD_SIZE:
        raise ValidationError(
            f'حجم الملف ({size / (1024*1024):.1f}MB) يتجاوز الحد المسموح ({MAX_UPLOAD_SIZE_MB}MB).'
        )


DOCUMENT_VALIDATORS = [
    document_extension_validator,
    validate_file_size,
    validate_upload_magic_bytes,
]


def validate_employee_upload(file):
    """يشغّل كل محققات رفع مستندات الموظفين/الطلبات."""
    if not file:
        return
    for validator in DOCUMENT_VALIDATORS:
        validator(file)


# ─── الصور (Avatars / شعار الشركة) ─────────────────────────────────────────
ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png']

image_extension_validator = FileExtensionValidator(
    allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
    message=f'صيغة الصورة غير مدعومة. الصيغ المسموحة: {", ".join(ALLOWED_IMAGE_EXTENSIONS)}',
)

MAX_IMAGE_SIZE_MB = 5
MAX_IMAGE_SIZE = MAX_IMAGE_SIZE_MB * 1024 * 1024


def validate_image_size(file):
    """تحقق من حجم الصور المرفوعة (5MB)."""
    if not file or not _is_new_upload(file):
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
