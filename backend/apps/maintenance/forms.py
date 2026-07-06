"""نماذج إدارة الصيانة."""
from django import forms

from apps.core.models import Branch
from apps.core.services.access_control import get_accessible_branch_ids
from apps.employees.models import Employee
from apps.maintenance.models import MaintenanceAsset, MaintenanceRequest, MaintenanceTrade, MaintenanceWorker


class MaintenanceRequestForm(forms.ModelForm):
    location_lat = forms.DecimalField(required=False, widget=forms.HiddenInput())
    location_lng = forms.DecimalField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = MaintenanceRequest
        fields = ('branch', 'asset', 'title', 'description', 'location', 'priority', 'attachment')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'hr-search-field__input w-full', 'placeholder': 'مثال: تكييف لا يعمل'}),
            'description': forms.Textarea(attrs={'class': 'hr-search-field__input w-full', 'rows': 3}),
            'location': forms.TextInput(attrs={
                'class': 'hr-search-field__input hr-location-picker__input w-full',
                'placeholder': 'العنوان الجغرافي أو ملاحظة إضافية (طابق، مبنى...)',
                'id': 'id_maintenance_location',
                'autocomplete': 'off',
            }),
            'priority': forms.Select(attrs={'class': 'hr-search-field__input w-full bg-white'}),
            'branch': forms.Select(attrs={'class': 'hr-search-field__input w-full bg-white'}),
            'asset': forms.Select(attrs={'class': 'hr-search-field__input w-full bg-white'}),
            'attachment': forms.FileInput(attrs={'class': 'hr-search-field__input w-full'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        qs = Branch.objects.filter(is_deleted=False, is_active=True).order_by('name')
        branch_ids = get_accessible_branch_ids(user) if user else None
        if branch_ids is not None:
            qs = qs.filter(pk__in=branch_ids)
        self.fields['branch'].queryset = qs
        if qs.count() == 1:
            self.fields['branch'].initial = qs.first().pk
        self.fields['asset'].queryset = MaintenanceAsset.objects.filter(
            is_deleted=False, is_active=True,
        ).order_by('name')
        self.fields['asset'].required = False
        self.fields['asset'].empty_label = '— اختر الأصل (اختياري) —'

    def clean(self):
        cleaned = super().clean()
        loc = (cleaned.get('location') or '').strip()
        lat = cleaned.get('location_lat')
        lng = cleaned.get('location_lng')
        if lat is not None and lng is not None:
            try:
                lat_f = float(lat)
                lng_f = float(lng)
            except (TypeError, ValueError):
                lat_f = lng_f = None
            if lat_f is not None and lng_f is not None:
                if -90 <= lat_f <= 90 and -180 <= lng_f <= 180:
                    maps = f'https://www.google.com/maps?q={lat_f:.6f},{lng_f:.6f}'
                    cleaned['location'] = f'{loc} | {maps}' if loc else maps
                else:
                    cleaned['location'] = loc
            else:
                cleaned['location'] = loc
        else:
            cleaned['location'] = loc
        return cleaned


class MaintenanceAssetForm(forms.ModelForm):
    class Meta:
        model = MaintenanceAsset
        fields = ('code', 'name', 'is_active')
        widgets = {
            'code': forms.TextInput(attrs={'class': 'hr-search-field__input w-full'}),
            'name': forms.TextInput(attrs={'class': 'hr-search-field__input w-full'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300'}),
        }


class MaintenanceTradeForm(forms.ModelForm):
    class Meta:
        model = MaintenanceTrade
        fields = ('code', 'name', 'is_active')
        widgets = {
            'code': forms.TextInput(attrs={'class': 'hr-search-field__input w-full'}),
            'name': forms.TextInput(attrs={'class': 'hr-search-field__input w-full'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300'}),
        }


class MaintenanceWorkerForm(forms.ModelForm):
    employee_id = forms.IntegerField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = MaintenanceWorker
        fields = ('name', 'phone', 'trade', 'is_active')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'hr-search-field__input w-full', 'placeholder': 'اسم العامل'}),
            'phone': forms.TextInput(attrs={'class': 'hr-search-field__input w-full', 'placeholder': '05xxxxxxxx'}),
            'trade': forms.Select(attrs={'class': 'hr-search-field__input w-full bg-white'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['trade'].queryset = MaintenanceTrade.objects.filter(
            is_deleted=False, is_active=True,
        ).order_by('name')
        if self.instance and self.instance.employee_id:
            self.fields['employee_id'].initial = self.instance.employee_id
        if not self.instance.pk:
            self.fields['is_active'].initial = True

    def clean(self):
        cleaned = super().clean()
        employee_id = cleaned.get('employee_id')
        name = (cleaned.get('name') or '').strip()
        phone = (cleaned.get('phone') or '').strip()

        employee = None
        if employee_id:
            employee = Employee.objects.filter(pk=employee_id, is_deleted=False).first()
            if not employee:
                self.add_error('employee_id', 'الموظف غير موجود.')
            else:
                if not name:
                    cleaned['name'] = employee.name
                if not phone and employee.phone:
                    cleaned['phone'] = employee.phone.strip()

        if not (cleaned.get('name') or '').strip():
            self.add_error('name', 'الاسم مطلوب (أو اختر موظفاً).')
        if not (cleaned.get('phone') or '').strip():
            self.add_error('phone', 'رقم الجوال مطلوب لإرسال واتساب.')
        cleaned['_employee'] = employee
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        employee = self.cleaned_data.get('_employee')
        instance.employee = employee
        if not instance.pk:
            instance.is_active = True
        if commit:
            instance.save()
        return instance


class WorkerReportForm(forms.Form):
    notes = forms.CharField(
        required=False,
        label='ملاحظات التنفيذ',
        widget=forms.Textarea(attrs={
            'class': 'maint-report__textarea',
            'rows': 4,
            'placeholder': 'وصف ما تم إنجازه (اختياري)',
            'id': 'id_notes',
        }),
    )
