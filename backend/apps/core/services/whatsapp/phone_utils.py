"""Normalize phone numbers for Evolution API (E.164 without +)."""
import re

from django.conf import settings

_ARABIC_DIGIT_TRANSLATION = str.maketrans({
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
})


def _default_country() -> str:
    return re.sub(r'\D', '', getattr(settings, 'WHATSAPP_DEFAULT_COUNTRY', '966') or '966')


def extract_digits(raw: str | None) -> str:
    """أرقام فقط — يدعم الأرقام العربية والفارسية."""
    text = str(raw or '').strip().translate(_ARABIC_DIGIT_TRANSLATION)
    return re.sub(r'\D', '', text)


def normalize_phone(raw: str | None, *, default_country: str | None = None) -> str:
    """
    Convert local/Saudi numbers to digits-only international format.
    Examples: 0512345678 → 966512345678, +966 51 234 5678 → 966512345678
    """
    digits = extract_digits(raw)
    if not digits:
        return ''

    country = re.sub(r'\D', '', default_country or _default_country())

    if digits.startswith('00'):
        digits = digits[2:]

    if country and digits.startswith(country):
        return digits

    if digits.startswith('0'):
        digits = digits[1:]

    if len(digits) == 9 and digits.startswith('5'):
        return f'{country}{digits}'

    return digits


def is_valid_phone(raw: str | None, *, default_country: str | None = None) -> bool:
    """رقم جوال سعودي صالح بعد التطبيع (966 + 9 أرقام تبدأ بـ 5)."""
    normalized = normalize_phone(raw, default_country=default_country)
    if not normalized:
        return False

    country = re.sub(r'\D', '', default_country or _default_country())
    if not normalized.startswith(country):
        return False

    local = normalized[len(country):]
    return len(local) == 9 and local.startswith('5')


def phone_field_error(raw: str | None, *, default_country: str | None = None) -> str | None:
    """رسالة خطأ عربية — أو None إذا الرقم صالح."""
    text = (raw or '').strip()
    if not text:
        return None

    digits = extract_digits(text)
    if not digits:
        return 'أدخل أرقاماً فقط.'

    country = re.sub(r'\D', '', default_country or _default_country())

    if is_valid_phone(text, default_country=country):
        return None

    if digits.startswith(country):
        local = digits[len(country):]
        if len(local) < 9:
            return 'الرقم ناقص — مثال: 966512345678.'
        return 'رقم غير صالح — مثال: 966512345678.'

    if digits.startswith('0'):
        if len(digits) < 10:
            return f'الرقم ناقص — يجب 10 أرقام مثل 0512345678 (أدخلت {len(digits)}).'
        return 'رقم غير صالح — مثال: 0512345678.'

    if digits.startswith('5'):
        if len(digits) < 9:
            return f'الرقم ناقص — مثال: 512345678 (أدخلت {len(digits)}).'
        return 'رقم غير صالح — مثال: 512345678.'

    return 'أدخل رقماً سعودياً — مثال: 0512345678 أو 966512345678.'
