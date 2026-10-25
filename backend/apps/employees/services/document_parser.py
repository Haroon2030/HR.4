"""استخراج البيانات من عقد التوظيف PDF."""
import re
from datetime import date
from decimal import Decimal
from typing import Optional

import pdfplumber


def extract_employment_contract_data(file_path: str) -> dict:
    """
    استخراج البيانات من عقد توظيف PDF (الصيغة السعودية الموحدة).

    المُرجع:
        {
            'success': bool,
            'error': str | None,
            'data': {
                'name': str,
                'id_number': str,
                'phone': str,
                'email': str,
                'gender': 'male'|'female',
                'nationality': str,
                'hire_date': 'YYYY-MM-DD',  # اليوم
                'basic_salary': Decimal,
                'salary_details': {
                    'basic': Decimal,
                    'housing': Decimal,
                    'transportation': Decimal,
                    'other': Decimal,
                    'total': Decimal
                }
            },
            'warnings': [str]
        }
    """
    warnings = []
    data = {}

    try:
        with pdfplumber.open(file_path) as pdf:
            # جمع نصوص جميع الصفحات
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += "\n" + text
    except Exception as e:
        return {
            'success': False,
            'error': f'خطأ في قراءة الملف: {str(e)}',
            'data': None,
            'warnings': []
        }

    # استخراج البيانات الشخصية
    data['name'] = _extract_employee_name(full_text) or ""
    data['id_number'] = _extract_id_number(full_text) or ""
    data['phone'] = _extract_phone(full_text) or ""
    data['email'] = _extract_email(full_text) or ""
    data['gender'] = _extract_gender(full_text) or ""
    data['nationality'] = _extract_nationality(full_text) or ""

    # استخراج الراتب
    salary_details = _extract_salary(full_text)
    data['basic_salary'] = salary_details.get('total') or salary_details.get('basic') or Decimal('0')
    data['salary_details'] = salary_details

    # تاريخ المباشرة — اليوم تلقائياً
    data['hire_date'] = date.today().strftime('%Y-%m-%d')

    # التحقق من البيانات الإجبارية
    if not data['name']:
        warnings.append('لم يتم استخراج اسم الموظف بشكل صحيح')
    if not data['id_number']:
        warnings.append('لم يتم استخراج رقم الهوية')
    if not data['basic_salary'] or data['basic_salary'] == Decimal('0'):
        warnings.append('لم يتم استخراج الراتب')

    return {
        'success': True,
        'error': None,
        'data': data,
        'warnings': warnings
    }


def _extract_employee_name(text: str) -> Optional[str]:
    """استخراج اسم الموظف."""
    # البحث عن "Employee name:" أو "اسم الموظف:"
    patterns = [
        r'Employee name:\s*([^\n]+?)(?:\n|:)',
        r'اسم الموظف:\s*([^\n]+?)(?:\n|:)',
        r'(?:Employee name|اسم الموظف)[:\s]+([A-Za-zء-ي\s]+?)(?:\n|Nationality|الجنسية)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            name = match.group(1).strip()
            # تنظيف النص من الأحرف الزائدة
            name = re.sub(r'[\s:]+$', '', name)
            if name and len(name) > 2:
                return name

    return None


def _extract_id_number(text: str) -> Optional[str]:
    """استخراج رقم الهوية."""
    # البحث عن "ID no.:" أو "رقم الهوية:"
    patterns = [
        r'ID no\.:\s*(\d{10})',
        r'رقم الهوية:\s*(\d{10})',
        r'(?:ID|رقم)\s+(?:no\.|الهوية)[:\s]+(\d{10})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def _extract_phone(text: str) -> Optional[str]:
    """استخراج رقم الهاتف."""
    # البحث عن "Mobile number:" أو "رقم الجوال:"
    patterns = [
        r'Mobile number:\s*([\d\s\-\+]+)',
        r'رقم الجوال:\s*([\d\s\-\+]+)',
        r'(?:Mobile|جوال)[:\s]+([\d\s\-\+]+?)(?:\n|E-mail|البريد)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            phone = match.group(1).strip()
            phone = re.sub(r'\s+', ' ', phone)
            if len(phone) > 8:
                return phone

    return None


def _extract_email(text: str) -> Optional[str]:
    """استخراج البريد الإلكتروني."""
    # البحث عن بريد إلكتروني بسيط
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    if match:
        return match.group(0)
    return None


def _extract_gender(text: str) -> Optional[str]:
    """استخراج الجنس."""
    # البحث عن "Gender: Male" أو "Gender: Female"
    if re.search(r'(?:Gender|جنس)[:\s]+(?:Male|ذكر|رجل)', text, re.IGNORECASE):
        return 'male'
    elif re.search(r'(?:Gender|جنس)[:\s]+(?:Female|أنثى|امرأة)', text, re.IGNORECASE):
        return 'female'
    return None


def _extract_nationality(text: str) -> Optional[str]:
    """استخراج الجنسية."""
    # البحث عن "Nationality: Saudi" أو "الجنسية: سعودي"
    patterns = [
        r'Nationality:\s*([A-Za-z]+)',
        r'الجنسية:\s*([^\n:]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def _extract_salary(text: str) -> dict:
    """استخراج تفاصيل الراتب."""
    result = {
        'basic': Decimal('0'),
        'housing': Decimal('0'),
        'transportation': Decimal('0'),
        'other': Decimal('0'),
        'total': Decimal('0'),
    }

    # استخراج الراتب الأساسي
    match = re.search(
        r'(?:Basic Wage|الراتب الأساسي)[:\s]+([0-9,]+\.?\d*)',
        text,
        re.IGNORECASE
    )
    if match:
        result['basic'] = _parse_decimal(match.group(1))

    # استخراج بدل السكن
    match = re.search(
        r'(?:Housing Allowance|بدل السكن|بدل (?:ة )?السكن)[:\s]+([0-9,]+\.?\d*)',
        text,
        re.IGNORECASE
    )
    if match:
        result['housing'] = _parse_decimal(match.group(1))

    # استخراج بدل المواصلات
    match = re.search(
        r'(?:Transportation|نقل|المواصلات)[:\s]+([0-9,]+\.?\d*)',
        text,
        re.IGNORECASE
    )
    if match:
        result['transportation'] = _parse_decimal(match.group(1))

    # استخراج الإجمالي
    match = re.search(
        r'(?:Total Wage|إجمالي الراتب|الراتب الإجمالي)[:\s]+([0-9,]+\.?\d*)',
        text,
        re.IGNORECASE
    )
    if match:
        result['total'] = _parse_decimal(match.group(1))

    # إذا لم نجد الإجمالي، احسبه
    if result['total'] == Decimal('0'):
        result['total'] = result['basic'] + result['housing'] + result['transportation'] + result['other']

    return result


def _parse_decimal(value: str) -> Decimal:
    """تحويل نص مع الفواصل إلى Decimal."""
    try:
        # إزالة الفواصل
        value = value.replace(',', '').strip()
        return Decimal(value)
    except:
        return Decimal('0')
