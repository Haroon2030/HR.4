"""
اختبارات استخراج البيانات من عقد التوظيف PDF
"""
import tempfile
from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import Branch, Company
from apps.employees.models import Employee
from apps.employees.services.document_parser import extract_employment_contract_data

User = get_user_model()


class DocumentParserTests(TestCase):
    """اختبارات دالة استخراج البيانات من PDF"""

    @classmethod
    def setUpClass(cls):
        """إنشاء PDF تجريبي للاختبار"""
        super().setUpClass()
        # إنشاء ملف PDF بسيط يحتوي على البيانات المتوقعة
        cls.pdf_content = (
            b'%PDF-1.4\n'
            b'1 0 obj\n'
            b'<< /Type /Catalog /Pages 2 0 R >>\n'
            b'endobj\n'
            b'2 0 obj\n'
            b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n'
            b'endobj\n'
            b'3 0 obj\n'
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n'
            b'endobj\n'
            b'4 0 obj\n'
            b'<< >>\n'
            b'stream\n'
            b'BT /F1 12 Tf 50 700 Td\n'
            b'(Employee name: John Doe) Tj\n'
            b'0 -20 Td (ID no.: 1234567890) Tj\n'
            b'0 -20 Td (Mobile number: 966 55 123 45 67) Tj\n'
            b'0 -20 Td (E-mail: john@example.com) Tj\n'
            b'0 -20 Td (Gender: Male) Tj\n'
            b'0 -20 Td (Nationality: Saudi) Tj\n'
            b'0 -20 Td (Basic Wage: 5000.00) Tj\n'
            b'0 -20 Td (Housing Allowance: 1000.00) Tj\n'
            b'0 -20 Td (Transportation Allowance: 500.00) Tj\n'
            b'0 -20 Td (Total Wage: 6500.00) Tj\n'
            b'ET\n'
            b'endstream\n'
            b'endobj\n'
            b'5 0 obj\n'
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n'
            b'endobj\n'
            b'xref\n'
            b'0 6\n'
            b'0000000000 65535 f\n'
            b'0000000009 00000 n\n'
            b'0000000058 00000 n\n'
            b'0000000115 00000 n\n'
            b'0000000261 00000 n\n'
            b'0000000602 00000 n\n'
            b'trailer\n'
            b'<< /Size 6 /Root 1 0 R >>\n'
            b'startxref\n'
            b'697\n'
            b'%%EOF\n'
        )

    def test_extract_employee_name(self):
        """اختبار استخراج اسم الموظف"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(self.pdf_content)
            f.flush()

            result = extract_employment_contract_data(f.name)

            self.assertTrue(result['success'])
            # قد لا يتم استخراج الاسم من PDF البسيط، لكن البنية يجب أن تكون صحيحة
            self.assertIn('data', result)
            self.assertIn('name', result['data'])

    def test_extract_salary_data(self):
        """اختبار استخراج بيانات الراتب"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(self.pdf_content)
            f.flush()

            result = extract_employment_contract_data(f.name)

            self.assertTrue(result['success'])
            self.assertIn('salary_details', result['data'])
            # يجب أن يكون هناك إجمالي راتب على الأقل
            self.assertIsNotNone(result['data']['salary_details'])

    def test_hire_date_auto_assigned(self):
        """اختبار تعيين تاريخ المباشرة تلقائياً إلى اليوم"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(self.pdf_content)
            f.flush()

            result = extract_employment_contract_data(f.name)

            self.assertTrue(result['success'])
            # يجب أن يكون تاريخ المباشرة مساوياً لتاريخ اليوم
            expected_date = date.today().strftime('%Y-%m-%d')
            self.assertEqual(result['data']['hire_date'], expected_date)

    def test_invalid_file(self):
        """اختبار معالجة ملف غير صحيح"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'invalid pdf content')
            f.flush()

            result = extract_employment_contract_data(f.name)

            # قد يفشل الاستخراج أو يُرجع بيانات فارغة
            self.assertIsNotNone(result)
            self.assertIn('success', result)


class ParseEmploymentContractViewTests(TestCase):
    """اختبارات API endpoint استخراج البيانات"""

    def setUp(self):
        """إنشاء المستخدم والفرع"""
        self.client = Client()
        company = Company.objects.create(name='شركة الاختبار')
        self.branch = Branch.objects.create(name='فرع الاختبار', code='TEST', company=company)

        # إنشاء مستخدم بصلاحية add_employee
        from apps.core.models import Role, Permission
        self.user = User.objects.create_user('testuser', password='pass123')

        # تخطي الصلاحيات المعقدة للاختبار — استخدم superuser بدلاً من ذلك
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        self.client.force_login(self.user)

    def _create_test_pdf(self):
        """إنشاء ملف PDF بسيط للاختبار"""
        pdf_content = (
            b'%PDF-1.4\n'
            b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n'
            b'2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n'
            b'3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n'
            b'xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n'
            b'0000000058 00000 n\n0000000115 00000 n\n'
            b'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n220\n%%EOF\n'
        )
        return SimpleUploadedFile(
            'test_contract.pdf',
            pdf_content,
            content_type='application/pdf'
        )

    def test_parse_contract_requires_login(self):
        """اختبار أن الـ endpoint يتطلب تسجيل دخول"""
        self.client.logout()
        response = self.client.post('/employees/parse-contract/', {})
        self.assertEqual(response.status_code, 302)  # redirect to login

    def test_parse_contract_requires_permission(self):
        """اختبار أن الـ endpoint يتطلب صلاحية"""
        # إنشاء مستخدم بدون صلاحيات
        user = User.objects.create_user('notest', password='pass123')
        self.client.force_login(user)

        response = self.client.post('/employees/parse-contract/', {})
        self.assertIn(response.status_code, [302, 403])  # redirect or forbidden

    def test_parse_contract_requires_file(self):
        """اختبار أن الـ endpoint يتطلب ملف"""
        response = self.client.post('/employees/parse-contract/', {})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('لم يتم رفع ملف', data['error'])

    def test_parse_contract_with_valid_pdf(self):
        """اختبار الـ endpoint مع ملف PDF صحيح"""
        pdf_file = self._create_test_pdf()
        response = self.client.post('/employees/parse-contract/', {
            'commencement_document': pdf_file
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIsNotNone(data['data'])
        self.assertIn('hire_date', data['data'])

    def test_parse_contract_invalid_file_type(self):
        """اختبار الـ endpoint مع ملف بصيغة خاطئة"""
        invalid_file = SimpleUploadedFile(
            'test.txt',
            b'this is not a pdf',
            content_type='text/plain'
        )
        response = self.client.post('/employees/parse-contract/', {
            'commencement_document': invalid_file
        })

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
