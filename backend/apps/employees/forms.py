"""
Forms لـ apps.employees - استبدال request.POST.get(...) المباشر.

EmployeeForm: ModelForm كامل لإنشاء/تعديل ملف موظف (32 حقل)
EmploymentRequestForm: نموذج طلب توظيف (الأخصائي يُرسله للمدير)
"""
from django import forms
from django.core.exceptions import ValidationError

from apps.employees.models import Employee, EmploymentRequest, EmployeeStatement


# 🏷️ خريطة عرض الحقول المرجعية (FK) في القوائم المنسدلة — الرقم/الكود ثم الاسم
def _code_then_name(obj):
    code = (getattr(obj, 'code', None) or '').strip()
    name = (getattr(obj, 'name', None) or '').strip()
    if code and name and code != name:
        return f"{code} — {name}"
    return code or name or str(obj)


def _name_only(obj):
    return getattr(obj, 'name', None) or str(obj)


FK_LABEL_OVERRIDES = {
    'branch': _code_then_name,
    'department': _code_then_name,
    'cost_center': _code_then_name,
    'nationality': _name_only,
    'profession': _name_only,
    'sponsorship': _name_only,
    'insurance': _name_only,
    'insurance_class': _name_only,
    'housing': _name_only,
    'bank': _name_only,
}


def _apply_fk_label_overrides(form):
    for fname, label_fn in FK_LABEL_OVERRIDES.items():
        f = form.fields.get(fname)
        if f is not None and hasattr(f, 'queryset'):
            f.label_from_instance = label_fn


# الحقول التي ستديرها الـ form (نستثني history + employment_request المُربَط لاحقاً)
# ⚠️ تحذير مهم: لا تُضِف هنا حقولاً تُحفظ عبر endpoints مستقلة (مثل work_schedule,
# statements, warnings). إذا أُضيفت هنا ولم تُرسَم في edit.html فإن form.save()
# سيمحو محتواها تلقائياً عند أي تعديل لحقل آخر.
_EMPLOYEE_FIELDS = [
    # نصوص أساسية
    'name', 'id_number', 'phone', 'email', 'employee_number',
    'gender',
    # FKs
    'nationality', 'profession', 'sponsorship', 'branch', 'department',
    'cost_center', 'insurance', 'insurance_class', 'housing',
    # تواريخ + حالة
    'hire_date', 'end_date', 'passport_expiry_date', 'status', 'end_reason',
    # الكرت الصحي
    'health_card_status', 'health_card_expiry',
    # راتب
    'basic_salary', 'housing_allowance', 'transport_allowance',
    'other_allowance', 'cash_amount', 'insurance_deduction_rate',
    'bank', 'iban',
    # إجازات (leaves_archive و attendance_notes معروضة كـ textarea في edit.html)
    'available_leave_balance', 'leaves_archive', 'attendance_notes',
    # ملفات
    'commencement_document', 'id_document', 'passport_document',
    'contract_document', 'other_documents',
    # ملاحظة: work_schedule, statements, warnings تُدار عبر endpoints مستقلة
    # (set_work_schedule, add_statement, ...) ولا تُدرج هنا لتجنّب المسح غير المقصود.
]


class EmployeeForm(forms.ModelForm):
    """ModelForm كامل لإنشاء/تعديل موظف.

    - يقبل request.POST + request.FILES.
    - الحقول الفارغة في request.POST تُعتبر «لم تُرسل» إذا لم تكن في self.data.
    - clean_name يضمن أن الاسم غير فارغ (مطلوب).
    """

    class Meta:
        model = Employee
        fields = _EMPLOYEE_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_fk_label_overrides(self)
        # كل الحقول اختيارية على مستوى الـ form باستثناء name
        # (Model أصلاً يسمح بـ blank=True/null=True لمعظمها)
        for field_name, field in self.fields.items():
            if field_name != 'name':
                field.required = False

        # 🛡️ حماية ضد المسح غير المقصود:
        # إذا كان النموذج يعدّل سجلاً موجوداً (instance.pk)، احذف من قائمة
        # الحقول كل حقل لم يُرسَل في POST وقيمته الحالية غير فارغة.
        # هذا يمنع ModelForm من كتابة "" فوق بيانات قديمة لمجرد أن القالب
        # لا يعرض حقلاً معيّناً.
        if self.instance and self.instance.pk and self.data:
            to_drop = []
            for field_name in list(self.fields.keys()):
                if field_name == 'name':
                    continue
                # الحقل غير موجود في الـ POST؟
                in_post = field_name in self.data or field_name in self.files
                if in_post:
                    continue
                # الحقل الحالي يحوي قيمة؟
                current = getattr(self.instance, field_name, None)
                if current not in (None, '', 0):
                    to_drop.append(field_name)
            for fname in to_drop:
                self.fields.pop(fname, None)

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('اسم الموظف مطلوب')
        return name

    def clean_email(self):
        # السماح بقيمة فارغة (model يسمح blank=True)
        return self.cleaned_data.get('email') or ''

    def clean_status(self):
        # الإبقاء على الحالة الحالية إذا لم تُرسل
        status = self.cleaned_data.get('status')
        if not status:
            return self.instance.status if self.instance and self.instance.pk else Employee.Status.ACTIVE
        return status


class EmploymentRequestForm(forms.ModelForm):
    """طلب توظيف يرسله الأخصائي لمدير الفرع."""

    class Meta:
        model = EmploymentRequest
        fields = ['name', 'branch', 'department', 'cost_center', 'commencement_document']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_fk_label_overrides(self)
        for field_name, field in self.fields.items():
            if field_name != 'name':
                field.required = False

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('اسم الموظف مطلوب')
        return name


# الحقول الإلزامية لإكمال الموافقة النهائية من الأخصائي
EMPLOYMENT_REQUEST_REQUIRED_FIELDS = [
    'id_number', 'phone', 'email', 'employee_number',
    'nationality', 'profession', 'sponsorship',
    'hire_date',
    'basic_salary', 'housing_allowance', 'transport_allowance',
    'id_document',
]


class EmploymentRequestEditForm(forms.ModelForm):
    """نموذج كامل لتعديل طلب التوظيف من قِبَل أخصائي الموارد قبل الموافقة النهائية.

    يشمل كل بيانات الموظف التي ستُنسخ إلى Employee عند الموافقة.
    الحقول في EMPLOYMENT_REQUEST_REQUIRED_FIELDS إلزامية على مستوى الـ form.
    """

    class Meta:
        model = EmploymentRequest
        fields = [
            # الحقول الأصلية
            'name', 'branch', 'department', 'cost_center', 'commencement_document',
            # بيانات أساسية
            'id_number', 'phone', 'email', 'employee_number',
            # Setup
            'nationality', 'profession', 'sponsorship', 'insurance', 'insurance_class',
            # تواريخ
            'hire_date', 'passport_expiry_date',
            # راتب
            'basic_salary', 'housing_allowance', 'transport_allowance',
            'other_allowance', 'cash_amount', 'insurance_deduction_rate',
            # مستندات
            'id_document', 'passport_document', 'contract_document', 'other_documents',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 🏷️ إظهار الاسم في القوائم المنسدلة بدلاً من الرقم/التمثيل الافتراضي
        _apply_fk_label_overrides(self)

        # اجعل كل الحقول اختيارية ابتداءً ثم اضبط الإلزامي
        for field_name, field in self.fields.items():
            field.required = False
        # تفعيل الإلزامي
        for field_name in EMPLOYMENT_REQUEST_REQUIRED_FIELDS:
            if field_name in self.fields:
                self.fields[field_name].required = True
        # الاسم دائماً إلزامي
        if 'name' in self.fields:
            self.fields['name'].required = True

        # 🎨 تطبيق ستايل Tailwind على كل widgets النموذج
        text_class = (
            'w-full px-3 py-2 border border-slate-300 rounded-md text-sm '
            'focus:ring-1 focus:ring-primary-500 focus:border-primary-500 outline-none'
        )
        file_class = (
            'block w-full text-xs text-slate-600 mt-1 '
            'file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 '
            'file:text-xs file:font-semibold file:bg-primary-50 file:text-primary-700 '
            'hover:file:bg-primary-100'
        )
        for field_name, field in self.fields.items():
            widget = field.widget
            cls = widget.__class__.__name__
            existing = widget.attrs.get('class', '')
            if cls in ('ClearableFileInput', 'FileInput'):
                widget.attrs['class'] = f'{existing} {file_class}'.strip()
            elif cls in ('Textarea',):
                widget.attrs['class'] = f'{existing} {text_class}'.strip()
                widget.attrs.setdefault('rows', 3)
            else:
                widget.attrs['class'] = f'{existing} {text_class}'.strip()
            # تحويل الحقول التاريخية إلى type="date"
            if field_name in ('hire_date', 'passport_expiry_date'):
                widget.input_type = 'date'
            # خطوة الأرقام للراتب
            if field_name in ('basic_salary', 'housing_allowance', 'transport_allowance',
                              'other_allowance', 'cash_amount', 'insurance_deduction_rate'):
                widget.attrs.setdefault('step', '0.01')
                widget.attrs.setdefault('min', '0')

        # 🛡️ حماية ضد المسح غير المقصود (نفس نمط EmployeeForm):
        # احذف الحقول التي لم تُرسَل في POST وقيمتها الحالية غير فارغة
        if self.instance and self.instance.pk and self.data:
            to_drop = []
            for field_name in list(self.fields.keys()):
                if field_name == 'name':
                    continue
                in_post = field_name in self.data or field_name in self.files
                if in_post:
                    continue
                current = getattr(self.instance, field_name, None)
                if current not in (None, '', 0):
                    to_drop.append(field_name)
            for fname in to_drop:
                self.fields.pop(fname, None)

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('اسم الموظف مطلوب')
        return name


class EmployeeStatementForm(forms.ModelForm):
    """نموذج إفادة/إنذار للموظف."""
    send_email = forms.BooleanField(required=False)
    employee_email = forms.EmailField(required=False)
    hr_email = forms.EmailField(required=False)

    class Meta:
        model = EmployeeStatement
        fields = ['statement_type', 'title', 'statement_date', 'content',
                  'employee_email', 'hr_email']

    def clean_title(self):
        v = (self.cleaned_data.get('title') or '').strip()
        if not v:
            raise ValidationError('عنوان الإفادة مطلوب')
        return v

    def clean_statement_date(self):
        # في حال تم تركه فارغاً نستخدم تاريخ اليوم
        from datetime import date
        return self.cleaned_data.get('statement_date') or date.today()

    def clean_send_email(self):
        return self.data.get('send_email') == '1'
