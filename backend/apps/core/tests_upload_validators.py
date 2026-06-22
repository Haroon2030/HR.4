"""اختبارات أمان رفع ملفات الموظفين."""
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.core.validators import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    validate_employee_upload,
    validate_upload_magic_bytes,
)


class EmployeeUploadValidatorTests(SimpleTestCase):
    def test_allowed_extensions_list(self):
        self.assertEqual(ALLOWED_DOCUMENT_EXTENSIONS, ['pdf', 'jpg', 'jpeg', 'png', 'xlsx'])

    def test_pdf_passes(self):
        f = SimpleUploadedFile('doc.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        validate_employee_upload(f)

    def test_jpg_passes(self):
        f = SimpleUploadedFile('photo.jpg', b'\xff\xd8\xff\xe0' + b'0' * 8, content_type='image/jpeg')
        validate_employee_upload(f)

    def test_png_passes(self):
        f = SimpleUploadedFile('scan.png', b'\x89PNG\r\n\x1a\n' + b'0' * 8, content_type='image/png')
        validate_employee_upload(f)

    def test_xlsx_passes(self):
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as archive:
            archive.writestr('xl/workbook.xml', '<workbook/>')
        f = SimpleUploadedFile('sheet.xlsx', buf.getvalue(), content_type='application/vnd.ms-excel')
        validate_employee_upload(f)

    def test_exe_rejected(self):
        f = SimpleUploadedFile('virus.exe', b'MZ' + b'0' * 8, content_type='application/octet-stream')
        with self.assertRaises(ValidationError):
            validate_employee_upload(f)

    def test_fake_pdf_rejected(self):
        f = SimpleUploadedFile('fake.pdf', b'not-a-pdf', content_type='application/pdf')
        with self.assertRaises(ValidationError):
            validate_upload_magic_bytes(f)

    def test_docx_rejected(self):
        f = SimpleUploadedFile('letter.docx', b'PK\x03\x04' + b'0' * 8, content_type='application/vnd.ms-word')
        with self.assertRaises(ValidationError):
            validate_employee_upload(f)
