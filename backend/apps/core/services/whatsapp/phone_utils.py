"""Normalize phone numbers for Evolution API (E.164 without +)."""
import re

from django.conf import settings


def normalize_phone(raw: str | None, *, default_country: str | None = None) -> str:
    """
    Convert local/Saudi numbers to digits-only international format.
    Examples: 0512345678 → 966512345678, +966 51 234 5678 → 966512345678
    """
    if not raw:
        return ''

    digits = re.sub(r'\D', '', str(raw).strip())
    if not digits:
        return ''

    country = (default_country or getattr(settings, 'WHATSAPP_DEFAULT_COUNTRY', '966') or '966')
    country = re.sub(r'\D', '', country)

    if digits.startswith('00'):
        digits = digits[2:]

    if country and digits.startswith(country):
        return digits

    if digits.startswith('0') and len(digits) >= 10:
        return f'{country}{digits[1:]}'

    if len(digits) == 9 and digits.startswith('5'):
        return f'{country}{digits}'

    return digits
