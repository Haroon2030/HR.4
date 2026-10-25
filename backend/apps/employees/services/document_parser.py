"""استخراج البيانات من عقد التوظيف PDF."""
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Optional

import pdfplumber


def extract_employment_contract_data(file_path: str, original_name: Optional[str] = None) -> dict:
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
    # بيانات الموظف في بند «الطرف الثاني» فقط (بند الطرف الأول بيانات الشركة)
    idx = full_text.find('Second Party')
    section = full_text[idx:idx + 3500] if idx != -1 else full_text
    clean = section.replace('\x00', '')

    data['name'] = _extract_employee_name(section) or ""
    if not data['name']:
        data['name'] = _ocr_employee_name(file_path) or ""
        if data['name']:
            warnings.append('قُرئ الاسم العربي بالتعرّف الضوئي (OCR) — راجعه قبل الحفظ')
    if not data['name']:
        fallback = _name_from_filename(original_name)
        if fallback:
            data['name'] = fallback
            warnings.append('تعذّرت قراءة الاسم العربي من العقد، أُخذ من اسم الملف — راجعه قبل الحفظ')
    data['name_en'] = transliterate_arabic_name(data['name'])
    if data['name_en']:
        warnings.append('الاسم الإنجليزي مُولَّد من الاسم العربي (العقد لا يحتويه) — راجعه')
    data['id_number'] = _extract_id_number(clean) or ""
    data['phone'] = _extract_phone(clean) or ""
    data['email'] = _extract_email(clean) or ""
    data['gender'] = _extract_gender(clean) or ""
    data['nationality'] = _extract_nationality(clean) or ""
    data['birth_date_hijri'] = _extract_birth_hijri(clean) or ""

    # استخراج الراتب
    salary_details = _extract_salary(full_text)
    data['basic_salary'] = salary_details.get('basic') or salary_details.get('total') or Decimal('0')
    data['salary_details'] = salary_details

    # تاريخ المباشرة — اليوم تلقائياً
    data['hire_date'] = date.today().strftime('%Y-%m-%d')

    # التحقق من البيانات الإجبارية
    if not data['name']:
        warnings.append('تعذّرت قراءة اسم الموظف من العقد — أدخله يدوياً')
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
            name = _repair_arabic(name)
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
            digits = re.sub(r'\D', '', phone)
            if digits.startswith('966'):
                digits = '0' + digits[3:]
            if len(digits) >= 9:
                return digits

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


_ARABIC_RE = re.compile(r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]')


def _repair_arabic(text: str) -> Optional[str]:
    """إصلاح نص عربي مخزّن بترتيب بصري بأحرف العرض. يُرجع None إن كان تالفاً."""
    if not _ARABIC_RE.search(text):
        return text
    if '�' in text or '\x00' in text:
        return None  # حروف مفقودة في خط الملف — لا يمكن استعادتها
    fixed = unicodedata.normalize('NFKC', text)[::-1]
    fixed = re.sub(r'\s+', ' ', fixed).strip()
    return fixed or None


def _name_from_filename(original_name: Optional[str]) -> Optional[str]:
    """اسم الملف كاحتياط إن كان حروفاً عربية ومسافات فقط."""
    if not original_name:
        return None
    stem = os.path.splitext(os.path.basename(original_name))[0].strip()
    if re.fullmatch(r'[ء-ي ]{3,100}', stem) and len(stem.split()) >= 2:
        return re.sub(r'\s+', ' ', stem)
    return None


# ── الجنسية: صيغة العقد الإنجليزية → اسم الجنسية في جدول الإعداد ──
NATIONALITY_EN_TO_AR = {
    'saudi': 'السعودية', 'yemeni': 'اليمن', 'egyptian': 'مصر', 'sudanese': 'السودان',
    'syrian': 'سوريا', 'indian': 'الهند', 'bangladeshi': 'بنغلاديش', 'jordanian': 'الاردن',
    'pakistani': 'باكستان', 'ethiopian': 'اثيوبيا', 'filipino': 'الفلبين', 'philippine': 'الفلبين',
    'indonesian': 'اندونيسيا',
}


# ── تحويل الاسم العربي إلى حروف لاتينية (للمراجعة اليدوية) ──
_NAME_WORDS = {
    'محمد': 'Mohammed', 'احمد': 'Ahmed', 'علي': 'Ali', 'عبدالله': 'Abdullah',
    'عبدالرحمن': 'Abdulrahman', 'عبدالعزيز': 'Abdulaziz', 'عبدالرحيم': 'Abdulrahim',
    'عبدالملك': 'Abdulmalik', 'عبدالمجيد': 'Abdulmajeed', 'عبدالكريم': 'Abdulkarim',
    'خالد': 'Khalid', 'فهد': 'Fahad', 'سعد': 'Saad', 'سعود': 'Saud', 'سلمان': 'Salman',
    'ناصر': 'Nasser', 'يوسف': 'Yousef', 'ابراهيم': 'Ibrahim', 'اسماعيل': 'Ismail',
    'عمر': 'Omar', 'عثمان': 'Othman', 'حسن': 'Hassan', 'حسين': 'Hussein', 'صالح': 'Saleh',
    'ماجد': 'Majed', 'فيصل': 'Faisal', 'سلطان': 'Sultan', 'نايف': 'Naif', 'تركي': 'Turki',
    'بندر': 'Bandar', 'راشد': 'Rashed', 'رشيد': 'Rasheed', 'سالم': 'Salem', 'مشعل': 'Mishaal',
    'ياسر': 'Yasser', 'زياد': 'Ziyad', 'طارق': 'Tariq', 'ماهر': 'Maher', 'نواف': 'Nawaf',
    'وليد': 'Waleed', 'هاني': 'Hani', 'عادل': 'Adel', 'ريان': 'Rayan', 'سامي': 'Sami',
    'عجلان': 'Ajlan', 'العجلان': 'Alajlan', 'مصطفى': 'Mustafa', 'جابر': 'Jaber',
    'بن': 'bin', 'ابن': 'Ibn', 'منصور': 'Mansour', 'مبارك': 'Mubarak', 'بدر': 'Badr', 'سعيد': 'Saeed', 'علاء': 'Alaa',
}
_LETTERS = {
    'ا': 'a', 'أ': 'a', 'إ': 'e', 'آ': 'a', 'ب': 'b', 'ت': 't', 'ث': 'th', 'ج': 'j', 'ح': 'h',
    'خ': 'kh', 'د': 'd', 'ذ': 'dh', 'ر': 'r', 'ز': 'z', 'س': 's', 'ش': 'sh', 'ص': 's', 'ض': 'd',
    'ط': 't', 'ظ': 'z', 'ع': 'a', 'غ': 'gh', 'ف': 'f', 'ق': 'q', 'ك': 'k', 'ل': 'l', 'م': 'm',
    'ن': 'n', 'ه': 'h', 'و': 'w', 'ي': 'y', 'ة': 'a', 'ى': 'a', 'ئ': 'e', 'ؤ': 'o',
}
_DIACRITICS_RE = re.compile(r'[\u064B-\u0652\u0640]')
_LETTER_VOWELS = set('aeiouy')


def _translit_word(word: str) -> str:
    word = _DIACRITICS_RE.sub('', word).replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    if word in _NAME_WORDS:
        return _NAME_WORDS[word]
    if word.startswith('ال') and len(word) > 3:
        return 'Al' + _translit_word(word[2:]).lower()
    out = ''
    for ch in word:
        piece = _LETTERS.get(ch, '')
        if out and piece and piece[0] not in _LETTER_VOWELS and out[-1] not in _LETTER_VOWELS:
            out += 'a'  # فاصل صوتي بين حرفين ساكنين
        out += piece
    return out[:1].upper() + out[1:]


def transliterate_arabic_name(name: Optional[str]) -> str:
    """نقل حرفي تقريبي للاسم العربي — للمراجعة اليدوية وليس مرجعاً رسمياً."""
    if not name or not _ARABIC_RE.search(name):
        return ''
    words = [_translit_word(w) for w in name.split() if w]
    result = re.sub(r'[^A-Za-z .\'\-]', '', ' '.join(words)).strip()
    return result if re.match(r"^[A-Za-z]", result) else ''


# ── قراءة الاسم العربي بالتعرّف الضوئي (OCR) عند تلف طبقة النص ──
_OCR_LABEL_RE = re.compile(r'اسم\s*العامل|Employee\s*name', re.IGNORECASE)
_OCR_NAME_RE = re.compile(r'[ء-ي]+(?:\s+[ء-ي]+)+')


def _find_tesseract() -> Optional[str]:
    """مسار tesseract: متغير TESSERACT_CMD، ثم PATH، ثم مسار ويندوز الافتراضي."""
    candidates = [
        os.environ.get('TESSERACT_CMD'),
        shutil.which('tesseract'),
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    ]
    return next((c for c in candidates if c and os.path.exists(c)), None)


def _tesseract_env() -> dict:
    env = dict(os.environ)
    local = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'tessdata')
    if not env.get('TESSDATA_PREFIX') and os.path.isdir(local):
        env['TESSDATA_PREFIX'] = local
    return env


def _ocr_employee_name(file_path: str) -> Optional[str]:
    """يقصّ سطر «Employee name» من الصفحة ويقرؤه بـ Tesseract (ara). يُرجع None عند أي فشل."""
    tesseract = _find_tesseract()
    if not tesseract:
        return None
    try:
        import pypdfium2 as pdfium
        with pdfplumber.open(file_path) as pdf:
            for index, page in enumerate(pdf.pages):
                words = page.extract_words()
                for i, word in enumerate(words[:-1]):
                    if word['text'].startswith('Employee') and words[i + 1]['text'].startswith('name'):
                        scale = 4
                        image = pdfium.PdfDocument(file_path)[index].render(scale=scale).to_pil()
                        row = image.crop((
                            0, max(0, int((word['top'] - 3) * scale)),
                            int(page.width * scale), int((word['bottom'] + 3) * scale),
                        ))
                        return _ocr_row(tesseract, row)
    except Exception:
        return None
    return None


def _ocr_row(tesseract: str, row_image) -> Optional[str]:
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    try:
        tmp.close()
        row_image.save(tmp.name)
        done = subprocess.run(
            [tesseract, tmp.name, 'stdout', '-l', 'ara+eng', '--psm', '7'],
            capture_output=True, env=_tesseract_env(), timeout=30,
        )
        text = done.stdout.decode('utf-8', 'replace')
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    text = _OCR_LABEL_RE.sub(' ', text.replace('‎', ' ').replace('‏', ' '))
    match = _OCR_NAME_RE.search(text)
    return re.sub(r'\s+', ' ', match.group(0)).strip() if match else None


def _extract_birth_hijri(text: str) -> Optional[str]:
    """تاريخ الميلاد الهجري (YYYY/MM/DD) كما في العقد."""
    match = re.search(r'Birth date:\s*(1[34]\d{2})/(\d{2})/(\d{2})', text, re.IGNORECASE)
    return f'{match.group(1)}/{match.group(2)}/{match.group(3)}' if match else None
