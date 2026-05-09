"""
نماذج الموظفين وطلبات التوظيف
"""
from django.db import models
from django.conf import settings
from simple_history.models import HistoricalRecords

from apps.core.models import BaseModel, Branch
from apps.core.validators import DOCUMENT_VALIDATORS
from apps.departments.models import Department
from apps.cost_centers.models import CostCenter


# ══════════════════════════════════════════════════════════════════════════════
# طلب التوظيف
# ══════════════════════════════════════════════════════════════════════════════
class EmploymentRequest(BaseModel):
    """طلب توظيف ينشئه الأخصائي وينتظر موافقة مدير الفرع"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'قيد المراجعة'  # legacy — تجري ترقيتها إلى PENDING_BRANCH
        PENDING_BRANCH = 'pending_branch', 'بانتظار مدير الفرع'
        PENDING_GM = 'pending_gm', 'بانتظار مدير الموارد'
        PENDING_OFFICER = 'pending_officer', 'بانتظار أخصائي الموارد'
        APPROVED = 'approved', 'مقبول'
        REJECTED = 'rejected', 'مرفوض'

    name = models.CharField("اسم الموظف", max_length=200)
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='employment_requests',
        verbose_name="الفرع", null=True, blank=True
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, related_name='employment_requests',
        verbose_name="القسم", null=True, blank=True
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.SET_NULL, related_name='employment_requests',
        verbose_name="مركز التكلفة", null=True, blank=True
    )
    commencement_document = models.FileField(
        "مستند المباشرة", upload_to='employment_requests/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    status = models.CharField(
        "الحالة", max_length=20, choices=Status.choices, default=Status.PENDING_BRANCH
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='requested_employments', verbose_name="مقدم الطلب",
        null=True, blank=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='reviewed_employments', verbose_name="تمت المراجعة بواسطة",
        null=True, blank=True
    )
    reviewed_at = models.DateTimeField("تاريخ المراجعة", null=True, blank=True)
    review_notes = models.TextField("ملاحظات المراجعة", blank=True)

    # ─ دورة الموافقات متعدّدة المراحل ───────────────────────────
    branch_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='branch_reviewed_employment_requests',
        verbose_name="مدير الفرع المراجِع", null=True, blank=True,
    )
    branch_reviewed_at = models.DateTimeField("تاريخ موافقة مدير الفرع", null=True, blank=True)
    branch_notes = models.TextField("ملاحظات مدير الفرع", blank=True)

    gm_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='gm_reviewed_employment_requests',
        verbose_name="مدير الموارد المراجِع", null=True, blank=True,
    )
    gm_reviewed_at = models.DateTimeField("تاريخ موافقة مدير الموارد", null=True, blank=True)
    gm_notes = models.TextField("ملاحظات مدير الموارد", blank=True)

    assigned_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='assigned_employment_requests',
        verbose_name="أخصائي الموارد المُسند", null=True, blank=True,
    )
    assigned_at = models.DateTimeField("تاريخ الإسناد", null=True, blank=True)
    officer_reviewed_at = models.DateTimeField("تاريخ موافقة الأخصائي", null=True, blank=True)
    officer_notes = models.TextField("ملاحظات الأخصائي", blank=True)

    # ─ بيانات الموظف الكاملة (يعبّيها الأخصائي قبل الموافقة النهائية) ────────
    # بيانات أساسية
    id_number = models.CharField("رقم الهوية", max_length=50, blank=True)
    phone = models.CharField("رقم الجوال", max_length=20, blank=True)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    employee_number = models.CharField("الرقم الوظيفي", max_length=50, blank=True)

    # Setup References
    nationality = models.ForeignKey(
        'setup.Nationality', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employment_requests', verbose_name="الجنسية"
    )
    profession = models.ForeignKey(
        'setup.Profession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employment_requests', verbose_name="المهنة"
    )
    sponsorship = models.ForeignKey(
        'setup.Sponsorship', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employment_requests', verbose_name="الكفالة"
    )
    insurance = models.ForeignKey(
        'setup.Insurance', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employment_requests', verbose_name="التأمين الطبي"
    )
    insurance_class = models.ForeignKey(
        'setup.InsuranceClass', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employment_requests', verbose_name="فئة التأمين"
    )

    # تواريخ
    hire_date = models.DateField("تاريخ المباشرة", null=True, blank=True)
    passport_expiry_date = models.DateField("تاريخ انتهاء الجواز", null=True, blank=True)

    # الراتب
    basic_salary = models.DecimalField(
        "الراتب الأساسي", max_digits=12, decimal_places=2, default=0
    )
    housing_allowance = models.DecimalField(
        "بدل سكن", max_digits=12, decimal_places=2, default=0
    )
    transport_allowance = models.DecimalField(
        "بدل نقل", max_digits=12, decimal_places=2, default=0
    )
    other_allowance = models.DecimalField(
        "بدل إضافي", max_digits=12, decimal_places=2, default=0
    )
    cash_amount = models.DecimalField(
        "كاش", max_digits=12, decimal_places=2, default=0
    )
    insurance_deduction_rate = models.DecimalField(
        "نسبة خصم التأمينات", max_digits=5, decimal_places=2, default=0
    )

    # المستندات
    id_document = models.FileField(
        "صورة الهوية", upload_to='employment_requests/id/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    passport_document = models.FileField(
        "جواز السفر", upload_to='employment_requests/passport/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    contract_document = models.FileField(
        "العقد", upload_to='employment_requests/contract/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    other_documents = models.FileField(
        "مستندات أخرى", upload_to='employment_requests/other/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "طلب توظيف"
        verbose_name_plural = "طلبات التوظيف"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


# ══════════════════════════════════════════════════════════════════════════════
# الموظف
# ══════════════════════════════════════════════════════════════════════════════
class Employee(BaseModel):
    """ملف الموظف الكامل"""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'على رأس العمل'
        LEAVE = 'leave', 'في إجازة'
        SUSPENDED = 'suspended', 'موقوف'
        TERMINATED = 'terminated', 'منتهي الخدمة'

    # ── بيانات أساسية ───────────────────────────────────────────
    name = models.CharField("الاسم", max_length=200)
    id_number = models.CharField("رقم الهوية", max_length=50, blank=True)
    phone = models.CharField("رقم الجوال", max_length=20, blank=True)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    employee_number = models.CharField("الرقم الوظيفي", max_length=50, blank=True)

    nationality = models.ForeignKey(
        'setup.Nationality', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="الجنسية"
    )
    profession = models.ForeignKey(
        'setup.Profession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="المهنة"
    )
    sponsorship = models.ForeignKey(
        'setup.Sponsorship', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="الكفالة"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='employee_records',
        verbose_name="الفرع", null=True, blank=True
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, related_name='employee_records',
        verbose_name="القسم", null=True, blank=True
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.SET_NULL, related_name='employee_records',
        verbose_name="مركز التكلفة", null=True, blank=True
    )
    insurance = models.ForeignKey(
        'setup.Insurance', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="التأمين الطبي"
    )
    insurance_class = models.ForeignKey(
        'setup.InsuranceClass', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="فئة التأمين"
    )
    housing = models.ForeignKey(
        'setup.Building', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="السكن"
    )

    class HealthCardStatus(models.TextChoices):
        AVAILABLE = 'available', 'متوفر'
        NOT_AVAILABLE = 'not_available', 'غير متوفر'

    health_card_status = models.CharField(
        "حالة الكرت الصحي", max_length=20,
        choices=HealthCardStatus.choices, default=HealthCardStatus.NOT_AVAILABLE, blank=True,
    )
    health_card_expiry = models.DateField("تاريخ انتهاء الكرت الصحي", null=True, blank=True)

    hire_date = models.DateField("تاريخ المباشرة", null=True, blank=True)
    end_date = models.DateField("تاريخ التوقف", null=True, blank=True)
    passport_expiry_date = models.DateField("تاريخ انتهاء الجواز", null=True, blank=True)
    status = models.CharField(
        "حالة الموظف", max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    end_reason = models.CharField("سبب الانتهاء", max_length=100, blank=True)

    # ── الراتب ─────────────────────────────────────────────────
    basic_salary = models.DecimalField("الراتب الأساسي", max_digits=12, decimal_places=2, default=0)
    housing_allowance = models.DecimalField("بدل سكن", max_digits=12, decimal_places=2, default=0)
    transport_allowance = models.DecimalField("بدل نقل", max_digits=12, decimal_places=2, default=0)
    other_allowance = models.DecimalField("بدل إضافي", max_digits=12, decimal_places=2, default=0)
    cash_amount = models.DecimalField("كاش", max_digits=12, decimal_places=2, default=0)
    insurance_deduction_rate = models.DecimalField(
        "نسبة خصم التأمينات", max_digits=5, decimal_places=2, default=0
    )
    bank = models.ForeignKey(
        'setup.Bank', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="البنك"
    )
    iban = models.CharField("رقم الآيبان", max_length=34, blank=True)

    # ── الإجازات ───────────────────────────────────────────────
    available_leave_balance = models.DecimalField(
        "رصيد الإجازات المتوفر", max_digits=6, decimal_places=1, default=0
    )
    leaves_archive = models.TextField("أرشيف الإجازات", blank=True)

    # ── الجدول والإفادات ───────────────────────────────────────
    attendance_notes = models.TextField("الحضور والانصراف الشهري", blank=True)
    work_schedule = models.TextField("جدول الدوام", blank=True)
    statements = models.TextField("الإفادات", blank=True)
    warnings = models.TextField("الإنذارات", blank=True)

    # ── المستندات ──────────────────────────────────────────────
    commencement_document = models.FileField(
        "مستند المباشرة", upload_to='employees/commencement/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    id_document = models.FileField(
        "صورة الهوية", upload_to='employees/id/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    passport_document = models.FileField(
        "جواز السفر", upload_to='employees/passport/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    contract_document = models.FileField(
        "العقد", upload_to='employees/contract/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    other_documents = models.FileField(
        "مستندات أخرى", upload_to='employees/other/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    # ── الربط بطلب التوظيف ─────────────────────────────────────
    employment_request = models.OneToOneField(
        EmploymentRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employee', verbose_name="طلب التوظيف الأصلي"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "موظف"
        verbose_name_plural = "الموظفين"
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_salary(self):
        return (
            self.basic_salary + self.housing_allowance + self.transport_allowance
            + self.other_allowance + self.cash_amount
        )

    @property
    def accrued_leave_days(self):
        """رصيد الإجازات المستحق: 21 يوم سنوياً من تاريخ المباشرة (يُحسب فقط إذا كانت الكفالة معبّأة)."""
        if not self.hire_date or not self.sponsorship_id:
            return 0
        from django.utils import timezone
        from decimal import Decimal
        end = self.end_date or timezone.localdate()
        days = (end - self.hire_date).days
        if days <= 0:
            return Decimal('0.0')
        return (Decimal(days) / Decimal('365.25') * Decimal('21')).quantize(Decimal('0.1'))

    @property
    def remaining_leave_days(self):
        """الرصيد المتبقي = المستحق - المستخدم (لا يقل عن صفر)."""
        from decimal import Decimal
        accrued = Decimal(self.accrued_leave_days or 0)
        used = Decimal(self.available_leave_balance or 0)
        remaining = accrued - used
        if remaining < 0:
            remaining = Decimal('0')
        return remaining.quantize(Decimal('0.1'))

    @property
    def daily_wage(self):
        """الأجر اليومي = إجمالي الراتب ÷ 30."""
        from decimal import Decimal
        return (Decimal(self.total_salary or 0) / Decimal('30')).quantize(Decimal('0.01'))

    @property
    def leave_compensation(self):
        """بدل الإجازة عند التصفية = الرصيد المتبقي × الأجر اليومي (حد أقصى 21 يوم/سنة)."""
        from decimal import Decimal
        if not self.sponsorship_id:
            return Decimal('0.00')
        return (Decimal(self.remaining_leave_days or 0) * self.daily_wage).quantize(Decimal('0.01'))


# ══════════════════════════════════════════════════════════════════════════════
# إفادة / إنذار للموظف
# ══════════════════════════════════════════════════════════════════════════════
class EmployeeStatement(BaseModel):
    """إفادة أو إنذار يُسجَّل على الموظف ويُعرض في أرشيفه."""

    class StatementType(models.TextChoices):
        STATEMENT = 'statement', 'إفادة'
        WARNING = 'warning', 'إنذار'
        FINAL_WARNING = 'final_warning', 'إنذار نهائي'
        ACKNOWLEDGMENT = 'acknowledgment', 'إقرار'
        TERMINATE = 'terminate', 'تصفية'
        REACTIVATE = 'reactivate', 'إعادة تفعيل'
        SALARY_ADJUST = 'salary_adjust', 'تعديل راتب'
        TRANSFER = 'transfer', 'نقل'
        OTHER = 'other', 'أخرى'

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='statements_log',
        verbose_name="الموظف"
    )
    statement_type = models.CharField(
        "النوع", max_length=20, choices=StatementType.choices, default=StatementType.STATEMENT
    )
    title = models.CharField("العنوان", max_length=255)
    statement_date = models.DateField("التاريخ")
    content = models.TextField("التفاصيل", blank=True)
    document = models.FileField(
        "مستند مرفق", upload_to='employees/statements/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    serial_number = models.CharField(
        "الرقم المتسلسل", max_length=30, blank=True, db_index=True,
        help_text="مثال: STM-2026-0001"
    )
    employee_email = models.EmailField("بريد الموظف للإرسال", blank=True)
    hr_email = models.EmailField("بريد الموارد البشرية", blank=True)
    email_sent_at = models.DateTimeField("تاريخ إرسال الإيميل", null=True, blank=True)
    email_error = models.TextField("خطأ الإرسال", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_statements', verbose_name="أُضيفت بواسطة"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "إفادة / إنذار"
        verbose_name_plural = "الإفادات والإنذارات"
        ordering = ['-statement_date', '-created_at']

    def __str__(self):
        return f"{self.employee.name} — {self.get_statement_type_display()}: {self.title}"

    @classmethod
    def generate_serial(cls, statement_type, year=None):
        """يولّد رقم متسلسل سنوي مثل STM-2026-0001 (مرتبط بالنوع والسنة)."""
        from datetime import date
        prefix_map = {
            'statement': 'STM',
            'warning': 'WRN',
            'final_warning': 'FWR',
            'acknowledgment': 'ACK',
            'terminate': 'TRM',
            'reactivate': 'RAC',
            'salary_adjust': 'SAL',
            'transfer': 'TRF',
            'other': 'OTH',
        }
        prefix = prefix_map.get(statement_type, 'STM')
        year = year or date.today().year
        last = cls.objects.filter(
            serial_number__startswith=f'{prefix}-{year}-'
        ).order_by('-serial_number').first()
        next_num = 1
        if last and last.serial_number:
            try:
                next_num = int(last.serial_number.rsplit('-', 1)[-1]) + 1
            except (ValueError, IndexError):
                next_num = 1
        return f'{prefix}-{year}-{next_num:04d}'


# ══════════════════════════════════════════════════════════════════════════════
# إجازة موظف
# ══════════════════════════════════════════════════════════════════════════════
class EmployeeLeave(BaseModel):
    """طلب إجازة مُسجَّل على الموظف."""

    class LeaveType(models.TextChoices):
        ANNUAL = 'annual', 'إجازة سنوية'
        SICK = 'sick', 'إجازة مرضية'
        UNPAID = 'unpaid', 'إجازة بدون راتب'
        EMERGENCY = 'emergency', 'إجازة طارئة'
        OTHER = 'other', 'أخرى'

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='leaves_log',
        verbose_name="الموظف"
    )
    leave_type = models.CharField(
        "نوع الإجازة", max_length=20, choices=LeaveType.choices, default=LeaveType.ANNUAL
    )
    date_from = models.DateField("من تاريخ")
    date_to = models.DateField("إلى تاريخ")
    days = models.DecimalField("عدد الأيام", max_digits=6, decimal_places=1, default=0)
    notes = models.TextField("ملاحظات", blank=True)
    document = models.FileField(
        "مستند مرفق", upload_to='employees/leaves/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_leaves', verbose_name="أُضيفت بواسطة"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "إجازة موظف"
        verbose_name_plural = "إجازات الموظفين"
        ordering = ['-date_from', '-created_at']

    def __str__(self):
        return f"{self.employee.name} — {self.get_leave_type_display()} ({self.date_from} → {self.date_to})"

