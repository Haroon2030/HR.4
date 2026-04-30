"""
Forms لـ apps.employees - استبدال request.POST.get(...) المباشر.

EmployeeForm: ModelForm كامل لإنشاء/تعديل ملف موظف (32 حقل)
EmploymentRequestForm: نموذج طلب توظيف (الأخصائي يُرسله للمدير)
"""
from django import forms
from django.core.exceptions import ValidationError

from apps.employees.models import Employee, EmploymentRequest, EmployeeStatement


# الحقول التي ستديرها الـ form (نستثني history + employment_request المُربَط لاحقاً)
# ⚠️ تحذير مهم: لا تُضِف هنا حقولاً تُحفظ عبر endpoints مستقلة (مثل work_schedule,
# statements, warnings). إذا أُضيفت هنا ولم تُرسَم في edit.html فإن form.save()
# سيمحو محتواها تلقائياً عند أي تعديل لحقل آخر.
_EMPLOYEE_FIELDS = [
    # نصوص أساسية
    'name', 'id_number', 'phone', 'email', 'employee_number',
    # FKs
    'nationality', 'profession', 'sponsorship', 'branch', 'department',
    'cost_center', 'insurance', 'insurance_class',
    # تواريخ + حالة
    'hire_date', 'end_date', 'passport_expiry_date', 'status', 'end_reason',
    # راتب
    'basic_salary', 'housing_allowance', 'transport_allowance',
    'other_allowance', 'cash_amount', 'insurance_deduction_rate',
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
        for field_name, field in self.fields.items():
            if field_name != 'name':
                field.required = False

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
