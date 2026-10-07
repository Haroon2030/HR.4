"""تفقيط المبالغ بالعربية للنماذج الرسمية (ريال سعودي)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_UNITS = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة']
_TEENS = [
    'عشرة', 'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر', 'خمسة عشر',
    'ستة عشر', 'سبعة عشر', 'ثمانية عشر', 'تسعة عشر',
]
_TENS = ['', '', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون', 'ستون', 'سبعون', 'ثمانون', 'تسعون']
_HUNDREDS = [
    '', 'مائة', 'مائتان', 'ثلاثمائة', 'أربعمائة', 'خمسمائة',
    'ستمائة', 'سبعمائة', 'ثمانمائة', 'تسعمائة',
]

# (مفرد، مثنى، جمع 3-10)
_SCALES = [
    None,
    ('ألف', 'ألفان', 'آلاف'),
    ('مليون', 'مليونان', 'ملايين'),
    ('مليار', 'ملياران', 'مليارات'),
]


def _below_thousand(n: int) -> str:
    """نص العدد من 1 إلى 999."""
    parts: list[str] = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if rest:
        if rest < 10:
            parts.append(_UNITS[rest])
        elif rest < 20:
            parts.append(_TEENS[rest - 10])
        else:
            tens, unit = divmod(rest, 10)
            if unit:
                parts.append(f'{_UNITS[unit]} و{_TENS[tens]}')
            else:
                parts.append(_TENS[tens])
    return ' و'.join(parts)


def integer_in_words(n: int) -> str:
    """العدد الصحيح (0 ≤ n < 10^12) بالعربية."""
    if n == 0:
        return 'صفر'
    groups: list[int] = []
    while n:
        n, g = divmod(n, 1000)
        groups.append(g)
    parts: list[str] = []
    for index in range(len(groups) - 1, -1, -1):
        g = groups[index]
        if not g:
            continue
        if index == 0:
            parts.append(_below_thousand(g))
            continue
        singular, dual, plural = _SCALES[index]
        if g == 1:
            parts.append(singular)
        elif g == 2:
            parts.append(dual)
        elif 3 <= g <= 10:
            parts.append(f'{_below_thousand(g)} {plural}')
        else:
            parts.append(f'{_below_thousand(g)} {singular}')
    return ' و'.join(parts)


def amount_in_words(value, *, currency: str = 'ريال سعودي', subunit: str = 'هللة') -> str:
    """مثال: 5000 → «خمسة آلاف ريال سعودي فقط لا غير». يعيد '' لقيمة غير صالحة."""
    try:
        amount = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return ''
    if amount < 0 or amount >= Decimal('1000000000000'):
        return ''
    whole = int(amount)
    fraction = int((amount - whole) * 100)
    text = f'{integer_in_words(whole)} {currency}'
    if fraction:
        text += f' و{integer_in_words(fraction)} {subunit}'
    return f'{text} فقط لا غير'
