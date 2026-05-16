"""
Django Forms - التحقق من صحة المدخلات للعمليات الحساسة
يُستخدم في طبقة الـ web_views لاستبدال request.POST.get(...) المباشر
بآلية Form/ModelForm آمنة وموحّدة.

ملاحظة: القوالب تستخدم HTML خام، فالنماذج هنا تُستعمل للتحقق فقط
ولا تُمرَّر إلى template (نستخدم form.cleaned_data أو form.save()).
"""
from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal

from apps.core.models import Role, Branch
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


User = get_user_model()


# ──────────────────────────────────────────────────────────────────────
# Role
# ──────────────────────────────────────────────────────────────────────
class RoleForm(forms.ModelForm):
    is_active = forms.BooleanField(required=False)

    class Meta:
        model = Role
        fields = ['name', 'role_type', 'description', 'is_active']

    def clean_is_active(self):
        # خانة الاختيار في القالب ترسل '1' عند التفعيل
        v = self.data.get('is_active')
        return v == '1' or v is True

    def clean_role_type(self):
        role_type = self.cleaned_data.get('role_type')
        valid = {choice[0] for choice in Role.RoleType.choices}
        if role_type not in valid:
            raise ValidationError('نوع الدور غير صالح')
        return role_type


# ──────────────────────────────────────────────────────────────────────
# Branch
# ──────────────────────────────────────────────────────────────────────
class BranchForm(forms.ModelForm):
    is_active = forms.BooleanField(required=False)
    manager = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=True,
        error_messages={'required': 'يجب تحديد مدير للفرع'},
    )

    class Meta:
        model = Branch
        fields = ['name', 'code', 'manager', 'is_active']

    def clean_is_active(self):
        v = self.data.get('is_active')
        return v == '1' or v is True

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise ValidationError('رمز الفرع مطلوب')
        qs = Branch.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f'رمز الفرع "{code}" مستخدم بالفعل')
        return code

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('اسم الفرع مطلوب')
        return name


# ──────────────────────────────────────────────────────────────────────
# User (إنشاء + تعديل)
# ──────────────────────────────────────────────────────────────────────
class UserBaseForm(forms.Form):
    """قاعدة مشتركة لنماذج المستخدم (لا نستخدم ModelForm لاحتواء قواعد خاصة)"""
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    is_active = forms.BooleanField(required=False)

    role = forms.ModelChoiceField(queryset=Role.objects.filter(is_active=True), required=False)
    branch = forms.ModelChoiceField(queryset=Branch.objects.filter(is_active=True), required=False)

    user_number = forms.CharField(max_length=20, required=False)
    phone = forms.CharField(max_length=20, required=False)
    position = forms.CharField(max_length=100, required=False)

    assigned_branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.filter(is_active=True),
        required=False,
    )

    def clean_is_active(self):
        v = self.data.get('is_active')
        # إذا الحقل غير مرسل أصلاً نعيد None ليتم التعامل مع ذلك في الـ view
        if 'is_active' not in self.data:
            return None
        return v == '1' or v is True

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip()
        if not username:
            raise ValidationError('اسم المستخدم مطلوب')
        return username

    def clean_user_number(self):
        v = (self.cleaned_data.get('user_number') or '').strip()
        return v or None


class UserCreateForm(UserBaseForm):
    password = forms.CharField(min_length=4, required=True,
                               error_messages={'required': 'كلمة المرور مطلوبة'})

    def clean_username(self):
        username = super().clean_username()
        if User.objects.filter(username=username).exists():
            raise ValidationError(f'اسم المستخدم "{username}" موجود بالفعل')
        return username


class UserEditForm(UserBaseForm):
    password = forms.CharField(required=False)  # اختياري عند التعديل

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = super().clean_username()
        qs = User.objects.filter(username=username)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f'اسم المستخدم "{username}" موجود بالفعل')
        return username


# ──────────────────────────────────────────────────────────────────────
# Cost Center
# ──────────────────────────────────────────────────────────────────────
class CostCenterForm(forms.ModelForm):
    class Meta:
        model = CostCenter
        fields = ['code', 'name']

    def __init__(self, *args, branch=None, **kwargs):
        self.branch = branch
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise ValidationError('رمز المركز مطلوب')
        qs = CostCenter.objects.filter(code=code, is_deleted=False)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f'رمز المركز "{code}" موجود بالفعل')
        return code

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('اسم المركز مطلوب')
        return name


# ──────────────────────────────────────────────────────────────────────
# Department
# ──────────────────────────────────────────────────────────────────────
class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['code', 'name']

    def __init__(self, *args, branch=None, **kwargs):
        self.branch = branch
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise ValidationError('رمز القسم مطلوب')
        qs = Department.objects.filter(code=code, is_deleted=False)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f'رمز القسم "{code}" موجود بالفعل')
        return code

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('اسم القسم مطلوب')
        return name


# ──────────────────────────────────────────────────────────────────────
# Pending Action workflow forms (تُولّد payload لـ PendingAction)
# ──────────────────────────────────────────────────────────────────────

class LeaveRequestForm(forms.Form):
    """تقديم إجازة للموظف."""
    LEAVE_TYPES = [
        ('annual', 'سنوية'), ('sick', 'مرضية'),
        ('unpaid', 'بدون راتب'), ('emergency', 'طارئة'), ('other', 'أخرى'),
    ]
    leave_type = forms.ChoiceField(choices=LEAVE_TYPES, required=False)
    date_from = forms.DateField(error_messages={'invalid': 'تاريخ البداية غير صحيح', 'required': 'تاريخ البداية مطلوب'})
    date_to = forms.DateField(error_messages={'invalid': 'تاريخ النهاية غير صحيح', 'required': 'تاريخ النهاية مطلوب'})
    notes = forms.CharField(required=False)

    def clean_leave_type(self):
        return self.cleaned_data.get('leave_type') or 'annual'

    def clean(self):
        cd = super().clean()
        d_from = cd.get('date_from')
        d_to = cd.get('date_to')
        if d_from and d_to and d_to < d_from:
            raise ValidationError('تاريخ النهاية يجب أن يكون بعد تاريخ البداية')
        return cd


class TerminateEmployeeForm(forms.Form):
    end_date = forms.DateField(error_messages={'invalid': 'تاريخ التصفية غير صحيح', 'required': 'تاريخ التصفية مطلوب'})
    end_reason = forms.CharField(required=False)

    def clean_end_reason(self):
        return (self.cleaned_data.get('end_reason') or '').strip()


class ContractEndForm(forms.Form):
    """نموذج انتهاء عقد بموجب نظام العمل مع مكافأة نهاية الخدمة."""
    TERMINATED_BY_CHOICES = [
        ('company', 'الشركة'),
        ('employee', 'الموظف (استقالة)'),
    ]
    end_date = forms.DateField(
        error_messages={'invalid': 'تاريخ الانتهاء غير صحيح', 'required': 'تاريخ الانتهاء مطلوب'}
    )
    terminated_by = forms.ChoiceField(
        choices=TERMINATED_BY_CHOICES,
        error_messages={'required': 'يجب تحديد الطرف المنهي'}
    )
    end_reason = forms.CharField(required=False)
    notes = forms.CharField(required=False)

    def clean_end_reason(self):
        return (self.cleaned_data.get('end_reason') or '').strip()

    def clean_notes(self):
        return (self.cleaned_data.get('notes') or '').strip()


class EndOfServiceForm(forms.Form):
    """نموذج تصفية نهاية خدمة أو استقالة."""
    TERMINATED_BY_CHOICES = [
        ('company', 'تصفية نهاية خدمة (من قِبل الشركة)'),
        ('employee', 'استقالة (من قِبل الموظف)'),
    ]
    end_date = forms.DateField(
        error_messages={'invalid': 'تاريخ التصفية غير صحيح', 'required': 'تاريخ التصفية مطلوب'}
    )
    terminated_by = forms.ChoiceField(
        choices=TERMINATED_BY_CHOICES,
        error_messages={'required': 'يجب تحديد نوع التصفية'}
    )
    end_reason = forms.CharField(required=False)
    notes = forms.CharField(required=False)

    def clean_end_reason(self):
        return (self.cleaned_data.get('end_reason') or '').strip()

    def clean_notes(self):
        return (self.cleaned_data.get('notes') or '').strip()

class ReactivateEmployeeForm(forms.Form):
    new_hire_date = forms.DateField(error_messages={'invalid': 'تاريخ المباشرة الجديد غير صحيح', 'required': 'تاريخ المباشرة الجديد مطلوب'})
    reactivation_reason = forms.CharField(error_messages={'required': 'سبب إعادة التفعيل مطلوب'})
    new_status = forms.ChoiceField(choices=[('active', 'نشط'), ('leave', 'إجازة')], required=False)

    def clean_reactivation_reason(self):
        v = (self.cleaned_data.get('reactivation_reason') or '').strip()
        if not v:
            raise ValidationError('سبب إعادة التفعيل مطلوب')
        return v

    def clean_new_status(self):
        v = self.cleaned_data.get('new_status')
        return v if v in ('active', 'leave') else 'active'


class SalaryAdjustForm(forms.Form):
    new_basic_salary = forms.DecimalField(
        min_value=0, max_digits=12, decimal_places=2,
        error_messages={'invalid': 'قيمة الراتب غير صحيحة', 'required': 'الراتب الجديد مطلوب',
                        'min_value': 'لا يمكن أن يكون الراتب بالسالب'}
    )
    effective_date = forms.DateField(error_messages={'invalid': 'تاريخ التعديل غير صحيح', 'required': 'تاريخ التعديل مطلوب'})
    reason = forms.CharField(error_messages={'required': 'سبب التعديل مطلوب'})

    def clean_reason(self):
        v = (self.cleaned_data.get('reason') or '').strip()
        if not v:
            raise ValidationError('سبب التعديل مطلوب')
        return v


class TransferEmployeeForm(forms.Form):
    transfer_date = forms.DateField(error_messages={'invalid': 'تاريخ النقل غير صحيح', 'required': 'تاريخ النقل مطلوب'})
    reason = forms.CharField(error_messages={'required': 'سبب النقل مطلوب'})
    new_branch = forms.ModelChoiceField(queryset=Branch.objects.all(), required=False,
                                        error_messages={'invalid_choice': 'الفرع المختار غير موجود'})
    new_department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False,
                                            error_messages={'invalid_choice': 'القسم المختار غير موجود'})

    def clean_reason(self):
        v = (self.cleaned_data.get('reason') or '').strip()
        if not v:
            raise ValidationError('سبب النقل مطلوب')
        return v


class CustodyReceiveForm(forms.Form):
    """استلام عهدة جديدة من الشركة."""
    item_name = forms.CharField(error_messages={'required': 'اسم العهدة مطلوب'})
    item_details = forms.CharField(required=False)
    quantity = forms.IntegerField(min_value=1, initial=1,
        error_messages={'invalid': 'الكمية غير صحيحة', 'min_value': 'الكمية يجب أن تكون 1 فأكثر'})
    estimated_value = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2, required=False,
        error_messages={'invalid': 'القيمة غير صحيحة', 'min_value': 'لا يمكن أن تكون القيمة بالسالب'})
    received_at = forms.DateField(error_messages={'invalid': 'تاريخ الاستلام غير صحيح', 'required': 'تاريخ الاستلام مطلوب'})
    notes = forms.CharField(required=False)

    def clean_item_name(self):
        v = (self.cleaned_data.get('item_name') or '').strip()
        if not v:
            raise ValidationError('اسم العهدة مطلوب')
        return v


class CustodyClearForm(forms.Form):
    """تصفية عهدة موجودة (إعادتها للشركة)."""
    custody_id = forms.IntegerField(error_messages={'required': 'يجب اختيار العهدة', 'invalid': 'العهدة غير صحيحة'})
    returned_at = forms.DateField(error_messages={'invalid': 'تاريخ الإعادة غير صحيح', 'required': 'تاريخ الإعادة مطلوب'})
    return_notes = forms.CharField(required=False)


class JobOfferForm(forms.Form):
    """إصدار عرض وظيفي / خطاب تعريف."""
    addressed_to = forms.CharField(error_messages={'required': 'الجهة الموجَّه إليها مطلوبة'})
    purpose = forms.CharField(required=False)
    issued_at = forms.DateField(error_messages={'invalid': 'تاريخ الإصدار غير صحيح', 'required': 'تاريخ الإصدار مطلوب'})
    notes = forms.CharField(required=False)

    def clean_addressed_to(self):
        v = (self.cleaned_data.get('addressed_to') or '').strip()
        if not v:
            raise ValidationError('الجهة الموجَّه إليها مطلوبة')
        return v


class BusinessTripForm(forms.Form):
    """تسجيل رحلة عمل."""
    destination = forms.CharField(error_messages={'required': 'الوجهة مطلوبة'})
    purpose = forms.CharField(error_messages={'required': 'الغرض مطلوب'})
    start_date = forms.DateField(error_messages={'invalid': 'تاريخ البداية غير صحيح', 'required': 'تاريخ البداية مطلوب'})
    end_date = forms.DateField(error_messages={'invalid': 'تاريخ النهاية غير صحيح', 'required': 'تاريخ النهاية مطلوب'})
    estimated_cost = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2, required=False,
        error_messages={'invalid': 'التكلفة غير صحيحة', 'min_value': 'لا يمكن أن تكون التكلفة بالسالب'})
    notes = forms.CharField(required=False)

    def clean_destination(self):
        v = (self.cleaned_data.get('destination') or '').strip()
        if not v:
            raise ValidationError('الوجهة مطلوبة')
        return v

    def clean_purpose(self):
        v = (self.cleaned_data.get('purpose') or '').strip()
        if not v:
            raise ValidationError('الغرض مطلوب')
        return v

    def clean(self):
        cd = super().clean()
        s = cd.get('start_date')
        e = cd.get('end_date')
        if s and e and e < s:
            raise ValidationError('تاريخ النهاية يجب أن يكون بعد تاريخ البداية')
        return cd


class LoanRequestForm(forms.Form):
    """تقديم سلفة موظف."""
    amount = forms.DecimalField(min_value=Decimal('0.01'), max_digits=12, decimal_places=2,
        error_messages={'required': 'مبلغ السلفة مطلوب', 'invalid': 'المبلغ غير صحيح',
                        'min_value': 'يجب أن يكون المبلغ أكبر من صفر'})
    monthly_deduction = forms.DecimalField(min_value=Decimal('0.01'), max_digits=12, decimal_places=2,
        error_messages={'required': 'الخصم الشهري مطلوب', 'invalid': 'الخصم غير صحيح',
                        'min_value': 'يجب أن يكون الخصم أكبر من صفر'})
    installments = forms.IntegerField(min_value=1, required=False,
        error_messages={'invalid': 'عدد الأقساط غير صحيح', 'min_value': 'لا يقل عن قسط واحد'})
    reason = forms.CharField(required=False)
    issued_at = forms.DateField(error_messages={'required': 'تاريخ الصرف مطلوب', 'invalid': 'تاريخ الصرف غير صحيح'})
    first_deduction_date = forms.DateField(required=False,
        error_messages={'invalid': 'تاريخ بداية الخصم غير صحيح'})
    notes = forms.CharField(required=False)

    def clean(self):
        cd = super().clean()
        amount = cd.get('amount')
        monthly = cd.get('monthly_deduction')
        if amount and monthly and monthly > amount:
            raise ValidationError('الخصم الشهري لا يمكن أن يكون أكبر من مبلغ السلفة')
        return cd


class AbsenceForm(forms.Form):
    """تسجيل غياب موظف."""
    absence_date = forms.DateField(error_messages={'required': 'تاريخ الغياب مطلوب', 'invalid': 'تاريخ الغياب غير صحيح'})
    days = forms.IntegerField(min_value=1, initial=1,
        error_messages={'required': 'عدد الأيام مطلوب', 'invalid': 'عدد الأيام غير صحيح',
                        'min_value': 'لا يقل عن يوم واحد'})
    reason = forms.CharField(required=False)
    notes = forms.CharField(required=False)


class ReviewNotesForm(forms.Form):
    """تستخدم في approve/reject - notes اختيارية للموافقة وإجبارية للرفض."""
    review_notes = forms.CharField(required=False)

    def __init__(self, *args, require_notes=False, **kwargs):
        self._require_notes = require_notes
        super().__init__(*args, **kwargs)

    def clean_review_notes(self):
        v = (self.cleaned_data.get('review_notes') or '').strip()
        if self._require_notes and not v:
            raise ValidationError('سبب الرفض مطلوب')
        return v


class ArabicPasswordChangeForm(PasswordChangeForm):
    """تغيير كلمة المرور — تسميات ورسائل عربية."""

    error_messages = {
        'password_mismatch': 'كلمتا المرور الجديدة غير متطابقتين.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = 'كلمة المرور الحالية'
        self.fields['new_password1'].label = 'كلمة المرور الجديدة'
        self.fields['new_password2'].label = 'تأكيد كلمة المرور الجديدة'
        self.fields['old_password'].error_messages = {
            'required': 'أدخل كلمة المرور الحالية.',
        }
        self.fields['new_password1'].error_messages = {
            'required': 'أدخل كلمة المرور الجديدة.',
        }
        self.fields['new_password2'].error_messages = {
            'required': 'أكد كلمة المرور الجديدة.',
        }
        self.fields['new_password2'].help_text = 'أعد إدخال كلمة المرور الجديدة للتأكيد.'

    def clean_old_password(self):
        try:
            return super().clean_old_password()
        except ValidationError:
            raise ValidationError(
                'كلمة المرور الحالية غير صحيحة.',
                code='password_incorrect',
            ) from None


class LoginForm(forms.Form):
    username = forms.CharField(
        label='اسم المستخدم',
        error_messages={'required': 'اسم المستخدم مطلوب'},
    )
    password = forms.CharField(
        label='كلمة المرور',
        error_messages={'required': 'كلمة المرور مطلوبة'},
    )
    remember = forms.BooleanField(required=False, label='تذكرني')
