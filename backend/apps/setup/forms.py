"""
Forms للنماذج الخاصة بـ apps.setup (Lookups).
كلها ModelForm بسيطة مع تحقق على الـ code (مع مراعاة البيانات الناعمة الحذف).
"""
from django import forms
from django.core.exceptions import ValidationError

from apps.setup.models import (
    Nationality, Profession, Sponsorship, Insurance, InsuranceClass,
    Building, Bank, Administration,
)


def _validate_unique_code(model, code, instance):
    """تحقق غير مكرر للـ code (يستثنى الحالي + المحذوف ناعماً)"""
    code = (code or '').strip()
    if not code:
        raise ValidationError('الرمز مطلوب')
    qs = model.objects.filter(code=code, is_deleted=False)
    if instance and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise ValidationError(f'الرمز "{code}" موجود بالفعل')
    return code


def _validate_required(value, field_label):
    value = (value or '').strip()
    if not value:
        raise ValidationError(f'{field_label} مطلوب')
    return value


class NationalityForm(forms.ModelForm):
    class Meta:
        model = Nationality
        fields = ['code', 'name']

    def clean_code(self):
        return _validate_unique_code(Nationality, self.cleaned_data.get('code'), self.instance)

    def clean_name(self):
        return _validate_required(self.cleaned_data.get('name'), 'اسم الجنسية')


class ProfessionForm(forms.ModelForm):
    class Meta:
        model = Profession
        fields = ['code', 'name']

    def clean_code(self):
        return _validate_unique_code(Profession, self.cleaned_data.get('code'), self.instance)

    def clean_name(self):
        return _validate_required(self.cleaned_data.get('name'), 'اسم المهنة')


class SponsorshipForm(forms.ModelForm):
    class Meta:
        model = Sponsorship
        fields = ['code', 'company_name']

    def clean_code(self):
        return _validate_unique_code(Sponsorship, self.cleaned_data.get('code'), self.instance)

    def clean_company_name(self):
        return _validate_required(self.cleaned_data.get('company_name'), 'اسم الشركة')


class InsuranceForm(forms.ModelForm):
    class Meta:
        model = Insurance
        fields = ['code', 'insurance_type']

    def clean_code(self):
        return _validate_unique_code(Insurance, self.cleaned_data.get('code'), self.instance)

    def clean_insurance_type(self):
        return _validate_required(self.cleaned_data.get('insurance_type'), 'نوع التأمين')


class InsuranceClassForm(forms.ModelForm):
    class Meta:
        model = InsuranceClass
        fields = ['code', 'class_type']

    def clean_code(self):
        return _validate_unique_code(InsuranceClass, self.cleaned_data.get('code'), self.instance)

    def clean_class_type(self):
        return _validate_required(self.cleaned_data.get('class_type'), 'نوع الفئة')


class BuildingForm(forms.ModelForm):
    class Meta:
        model = Building
        fields = [
            'code', 'name', 'address',
            'rent_cost', 'water_cost', 'electricity_cost', 'cleaning_cost',
            'transport_cost', 'furniture_cost', 'tools_cost',
            'notes', 'is_active',
        ]

    def clean_code(self):
        return _validate_unique_code(Building, self.cleaned_data.get('code'), self.instance)

    def clean_name(self):
        return _validate_required(self.cleaned_data.get('name'), 'اسم العمارة')


class BankForm(forms.ModelForm):
    class Meta:
        model = Bank
        fields = ['code', 'name']

    def clean_code(self):
        return _validate_unique_code(Bank, self.cleaned_data.get('code'), self.instance)

    def clean_name(self):
        return _validate_required(self.cleaned_data.get('name'), 'اسم البنك')


class AdministrationForm(forms.ModelForm):
    class Meta:
        model = Administration
        fields = ['code', 'name']

    def clean_code(self):
        return _validate_unique_code(Administration, self.cleaned_data.get('code'), self.instance)

    def clean_name(self):
        return _validate_required(self.cleaned_data.get('name'), 'اسم الإدارة')
