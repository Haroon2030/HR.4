"""
HTML widgets — تنسيق آمن لحقول الأرقام (type=number).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import forms


def format_decimal_for_number_input(value) -> str:
    """قيمة مناسبة لـ input type=number — دائماً بنقطة عشرية."""
    if value is None or value == '':
        return ''
    try:
        amount = Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, ValueError, TypeError):
        return ''
    return format(amount, 'f')


class DecimalNumberInput(forms.NumberInput):
    """NumberInput يعرض القيم العشرية بنقطة دائماً (متوافق مع HTML5)."""

    def format_value(self, value):
        if value in (None, ''):
            return ''
        return format_decimal_for_number_input(value)


def apply_decimal_number_widgets(form) -> None:
    """يُطبَّق على ModelForm/Form لضمان عرض القيم العشرية في حقول الرقم."""
    for field in form.fields.values():
        if not isinstance(field, (forms.DecimalField, forms.FloatField)):
            continue
        field.localize = False
        attrs = field.widget.attrs.copy()
        if isinstance(field, forms.DecimalField) and 'step' not in attrs:
            attrs.setdefault('step', '0.01')
        field.widget = DecimalNumberInput(attrs=attrs)
