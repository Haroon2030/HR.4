"""
Forms للنماذج الخاصة بـ apps.setup (Lookups).
كلها ModelForm بسيطة مع تحقق على الـ code (مع مراعاة البيانات الناعمة الحذف).
"""
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.setup.models import (
    Nationality, Profession, Sponsorship, Insurance, InsuranceClass,
    Building, Bank, Administration, OperationsReportSettings, EvolutionWhatsAppSettings,
    WorkflowWhatsAppSettings,
)
from apps.setup.operations_report_recipients import (
    OPERATIONS_REPORT_RECIPIENT_ROLES,
    ROLE_FIELD_PREFIX,
    WHATSAPP_ROLE_FIELD_PREFIX,
)
from apps.setup.workflow_whatsapp_recipients import (
    WORKFLOW_WHATSAPP_RECIPIENT_ROLES,
    WHATSAPP_ROLE_FIELD_PREFIX as WORKFLOW_WHATSAPP_PREFIX,
)
from apps.core.services.whatsapp import phone_utils


def _validate_unique_code(model, code, instance):
    """تحقق عدم تكرار الرمز (يشمل المحذوف ناعماً — القيد unique في DB يشملهما)."""
    code = (code or '').strip()
    if not code:
        raise ValidationError('الرمز مطلوب')
    qs = model.all_objects.filter(code=code)
    if instance and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    existing = qs.first()
    if existing:
        if getattr(existing, 'is_deleted', False):
            raise ValidationError(
                f'الرمز "{code}" مستخدم لسجل محذوف. اختر رمزاً آخر أو أعد تفعيل السجل القديم.'
            )
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
        fields = ['code', 'company_name', 'commercial_registration']

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.widgets import apply_decimal_number_widgets
        apply_decimal_number_widgets(self)

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
        fields = ['code', 'name', 'manager', 'report_recipient_role']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields['manager'].required = False
        self.fields['manager'].queryset = User.objects.filter(is_active=True).order_by('first_name', 'username')
        self.fields['manager'].label_from_instance = (
            lambda u: u.get_full_name().strip() or u.username
        )

    def clean_code(self):
        return _validate_unique_code(Administration, self.cleaned_data.get('code'), self.instance)

    def clean_name(self):
        return _validate_required(self.cleaned_data.get('name'), 'اسم الإدارة')


class OperationsReportSettingsForm(forms.ModelForm):
    send_time = forms.TimeField(
        label='وقت الإرسال',
        input_formats=['%H:%M:%S', '%H:%M'],
        widget=forms.TimeInput(
            format='%H:%M:%S',
            attrs={
                'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'type': 'time',
                'step': '1',
            },
        ),
    )

    class Meta:
        model = OperationsReportSettings
        fields = (
            'is_enabled',
            'send_via_whatsapp',
            'send_time',
            'include_pending',
            'include_completed',
        )
        widgets = {
            'is_enabled': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-primary-600'}),
            'send_via_whatsapp': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-primary-600'}),
            'include_pending': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-primary-600'}),
            'include_completed': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-primary-600'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        stored = self.instance.recipient_emails_map() if self.instance.pk else {}
        stored_phones = self.instance.recipient_phones_map() if self.instance.pk else {}
        for key, label in OPERATIONS_REPORT_RECIPIENT_ROLES:
            field_name = f'{ROLE_FIELD_PREFIX}{key}'
            saved_email = (stored.get(key, '') or '').strip() if self.instance.pk else ''
            self.fields[field_name] = forms.EmailField(
                label=label,
                required=False,
                widget=forms.EmailInput(attrs={
                    'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 placeholder:text-slate-400 placeholder:font-normal hr-recipient-email-input',
                    'placeholder': 'ادخل البريد الالكتروني',
                    'dir': 'ltr',
                    'data-recipient-role': key,
                    'data-saved-email': saved_email,
                    'data-linked': 'true' if saved_email else 'false',
                    # قسم فريد لكل دور — يمنع المتصفح من نسخ نفس البريد لكل الحقول
                    'autocomplete': f'section-operations-report-{key} email',
                }),
            )
            if self.instance.pk and not self.data:
                self.fields[field_name].initial = stored.get(key, '')

            phone_field = f'{WHATSAPP_ROLE_FIELD_PREFIX}{key}'
            saved_phone = (stored_phones.get(key, '') or '').strip() if self.instance.pk else ''
            self.fields[phone_field] = forms.CharField(
                label=f'{label} — واتساب',
                required=False,
                widget=forms.TextInput(attrs={
                    'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 placeholder:text-slate-400 placeholder:font-normal hr-recipient-phone-input',
                    'placeholder': '0512345678',
                    'dir': 'ltr',
                    'inputmode': 'tel',
                    'data-recipient-role': key,
                    'data-saved-phone': saved_phone,
                    'data-linked': 'true' if saved_phone else 'false',
                    'autocomplete': f'section-operations-report-{key} tel',
                }),
            )
            if self.instance.pk and not self.data:
                self.fields[phone_field].initial = stored_phones.get(key, '')

    def clean_send_time(self):
        value = self.cleaned_data.get('send_time')
        if value is None:
            raise ValidationError('حدّد وقت الإرسال.')
        return value

    def clean(self):
        cleaned = super().clean()
        has_email = any(
            (cleaned.get(f'{ROLE_FIELD_PREFIX}{key}') or '').strip()
            for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES
        )
        has_phone = any(
            (cleaned.get(f'{WHATSAPP_ROLE_FIELD_PREFIX}{key}') or '').strip()
            for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES
        )
        for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES:
            phone_field = f'{WHATSAPP_ROLE_FIELD_PREFIX}{key}'
            raw_phone = (cleaned.get(phone_field) or '').strip()
            if not raw_phone:
                continue
            err = phone_utils.phone_field_error(raw_phone)
            if err:
                self.add_error(phone_field, err)

        if cleaned.get('is_enabled') and not has_email and not (cleaned.get('send_via_whatsapp') and has_phone):
            raise ValidationError(
                'يجب تحديد بريد مستلم واحد على الأقل، أو تفعيل واتساب مع رقم جوال واحد على الأقل.'
            )
        if cleaned.get('send_via_whatsapp') and not has_phone:
            raise ValidationError('فعّلت واتساب — أدخل رقماً واحداً على الأقل في الجدول.')
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.recipient_emails = {
            key: (self.cleaned_data.get(f'{ROLE_FIELD_PREFIX}{key}') or '').strip()
            for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES
        }
        obj.recipient_phones = {
            key: (self.cleaned_data.get(f'{WHATSAPP_ROLE_FIELD_PREFIX}{key}') or '').strip()
            for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES
        }
        obj.recipient_email = obj.recipient_emails.get('system_manager', '')
        if commit:
            obj.save()
        return obj


class EvolutionWhatsAppSettingsForm(forms.ModelForm):
    api_key = forms.CharField(
        label='مفتاح API',
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                'class': 'hr-report-field w-full',
                'placeholder': 'اتركه فارغاً للإبقاء على المفتاح الحالي',
                'dir': 'ltr',
                'autocomplete': 'new-password',
            },
        ),
    )

    class Meta:
        model = EvolutionWhatsAppSettings
        fields = (
            'api_url',
            'instance_name',
            'is_enabled',
            'webhook_enabled',
        )
        widgets = {
            'api_url': forms.URLInput(attrs={
                'class': 'hr-report-field w-full',
                'placeholder': 'http://72.61.107.230:8081',
                'dir': 'ltr',
            }),
            'instance_name': forms.TextInput(attrs={
                'class': 'hr-report-field w-full',
                'placeholder': 'hr',
                'dir': 'ltr',
            }),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-primary-600'}),
            'webhook_enabled': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-primary-600'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['api_url'].label = 'رابط Evolution API (Server URL)'
        if self.instance.pk and self.instance.api_key_masked():
            self.fields['api_key'].help_text = f'المفتاح الحالي: {self.instance.api_key_masked()}'

    def clean_instance_name(self):
        import re
        name = (self.cleaned_data.get('instance_name') or '').strip()
        if name and not re.fullmatch(r'^[A-Za-z0-9._-]+$', name):
            raise ValidationError('اسم Instance يجب أن يكون إنجليزياً (حروف/أرقام/._-)')
        return name

    def clean_api_url(self):
        return (self.cleaned_data.get('api_url') or '').strip().rstrip('/')

    def save(self, commit=True):
        obj = super().save(commit=False)
        new_key = (self.cleaned_data.get('api_key') or '').strip()
        if new_key:
            obj.api_key = new_key
        if commit:
            obj.save()
        return obj


class WorkflowWhatsAppSettingsForm(forms.ModelForm):
    class Meta:
        model = WorkflowWhatsAppSettings
        fields = ('is_enabled',)
        widgets = {
            'is_enabled': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-primary-600'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        stored_phones = self.instance.recipient_phones_map() if self.instance.pk else {}
        for key, label in WORKFLOW_WHATSAPP_RECIPIENT_ROLES:
            phone_field = f'{WORKFLOW_WHATSAPP_PREFIX}{key}'
            self.fields[phone_field] = forms.CharField(
                label=f'{label} — واتساب',
                required=False,
                widget=forms.TextInput(attrs={
                    'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 placeholder:text-slate-400',
                    'placeholder': '0512345678',
                    'dir': 'ltr',
                    'inputmode': 'tel',
                }),
            )
            if self.instance.pk and not self.data:
                self.fields[phone_field].initial = stored_phones.get(key, '')

    def clean(self):
        cleaned = super().clean()
        for key, _ in WORKFLOW_WHATSAPP_RECIPIENT_ROLES:
            phone_field = f'{WORKFLOW_WHATSAPP_PREFIX}{key}'
            raw_phone = (cleaned.get(phone_field) or '').strip()
            if not raw_phone:
                continue
            err = phone_utils.phone_field_error(raw_phone)
            if err:
                self.add_error(phone_field, err)
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.recipient_phones = {
            key: (self.cleaned_data.get(f'{WORKFLOW_WHATSAPP_PREFIX}{key}') or '').strip()
            for key, _ in WORKFLOW_WHATSAPP_RECIPIENT_ROLES
        }
        if commit:
            obj.save()
        return obj
