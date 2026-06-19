"""تنسيق موحّد لحقول الإدخال — قوائم فارغة وبدون قيم افتراضية مربكة."""
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.forms.models import ModelChoiceField

_EMPTY_SELECT = ('', '-- اختر --')

_ZERO_DECIMAL_FIELDS = frozenset({
    'basic_salary',
    'housing_allowance',
    'transport_allowance',
    'other_allowance',
    'cash_amount',
    'meal_allowance',
    'insurance_deduction_rate',
})


def _instance_looks_incomplete(instance) -> bool:
    if instance is None or not getattr(instance, 'pk', None):
        return True
    id_number = (getattr(instance, 'id_number', None) or '').strip()
    return not id_number


def apply_hr_empty_input_defaults(form) -> None:
    """قوائم منسدلة تبدأ بـ «-- اختر --»، أرقام صفرية فارغة، بدون placeholders."""
    instance = getattr(form, 'instance', None)
    incomplete = _instance_looks_incomplete(instance)
    is_post = bool(getattr(form, 'data', None))

    for name, field in form.fields.items():
        if isinstance(field, ModelChoiceField):
            field.empty_label = '-- اختر --'

        widget_name = field.widget.__class__.__name__
        if widget_name in (
            'TextInput', 'EmailInput', 'NumberInput', 'DecimalNumberInput',
            'DateInput', 'DateTimeInput', 'Textarea',
        ):
            field.widget.attrs.setdefault('placeholder', '')

    for name in ('gender', 'health_card_status'):
        field = form.fields.get(name)
        if field is None or not hasattr(field, 'choices'):
            continue
        attrs = field.widget.attrs.copy()
        field.widget = forms.Select(attrs=attrs)
        choices = [(value, label) for value, label in field.choices if value != '']
        field.choices = [_EMPTY_SELECT, *choices]

    if is_post:
        return

    for name in _ZERO_DECIMAL_FIELDS:
        if name not in form.fields:
            continue
        val = form.initial.get(name)
        if val in (None, '', 0, Decimal('0')):
            form.initial[name] = ''
            continue
        if instance is not None:
            inst_val = getattr(instance, name, None)
            if inst_val in (None, 0, Decimal('0')):
                form.initial[name] = ''

    if not incomplete:
        return

    model = getattr(getattr(form, 'Meta', None), 'model', None)
    gender_field = form.fields.get('gender')
    if gender_field and model and hasattr(model, 'Gender'):
        if getattr(instance, 'gender', None) == model.Gender.MALE:
            form.initial['gender'] = ''

    health_field = form.fields.get('health_card_status')
    if health_field and model and hasattr(model, 'HealthCardStatus'):
        if getattr(instance, 'health_card_status', None) == model.HealthCardStatus.NOT_AVAILABLE:
            form.initial['health_card_status'] = ''
