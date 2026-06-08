"""
نماذج الموظفين وطلبات التوظيف
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from simple_history.models import HistoricalRecords
from django.utils import timezone

from apps.core.models import BaseModel, Branch
from apps.core.validators import DOCUMENT_VALIDATORS
from apps.departments.models import Department
from apps.cost_centers.models import CostCenter


# ══════════════════════════════════════════════════════════════════════════════
# طلب التوظيف
# ══════════════════════════════════════════════════════════════════════════════
class EmploymentRequest(BaseModel):
    """طلب توظيف ينشئه الأخصائي وينتظر موافقة مدير الفرع"""

    class Gender(models.TextChoices):
        MALE = 'male', 'ذكر'
        FEMALE = 'female', 'أنثى'

    class HealthCardStatus(models.TextChoices):
        AVAILABLE = 'available', 'متوفر'
        NOT_AVAILABLE = 'not_available', 'غير متوفر'

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
    administration = models.ForeignKey(
        'setup.Administration', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employment_requests', verbose_name="الإدارة",
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
    housing = models.ForeignKey(
        'setup.Building', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employment_requests', verbose_name="السكن",
    )

    gender = models.CharField(
        "الجنس", max_length=10, choices=Gender.choices, default=Gender.MALE, blank=True,
    )

    # تواريخ
    hire_date = models.DateField("تاريخ المباشرة", null=True, blank=True)
    medical_insurance_expiry_date = models.DateField(
        "تاريخ انتهاء التأمين الطبي", null=True, blank=True,
        help_text="تاريخ تجديد بوليصة التأمين الصحي للموظف.",
    )
    contract_expiry_date = models.DateField(
        "تاريخ انتهاء العقد", null=True, blank=True,
        help_text="تاريخ نهاية العقد المخطط.",
    )
    health_card_status = models.CharField(
        "حالة الكرت الصحي", max_length=20,
        choices=HealthCardStatus.choices, default=HealthCardStatus.NOT_AVAILABLE, blank=True,
    )
    health_card_expiry = models.DateField("تاريخ انتهاء الكرت الصحي", null=True, blank=True)

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
    meal_allowance = models.DecimalField(
        "بدل التغذية", max_digits=12, decimal_places=2, default=0,
        help_text="يُضاف لإجمالي الراتب والمسير، ولا يُحتسب ضمن مكافأة نهاية الخدمة.",
    )
    insurance_deduction_rate = models.DecimalField(
        "نسبة خصم التأمينات", max_digits=5, decimal_places=2, default=0
    )
    bank = models.ForeignKey(
        'setup.Bank', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employment_requests', verbose_name="البنك",
    )
    iban = models.CharField("رقم الآيبان", max_length=34, blank=True)

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

    class Gender(models.TextChoices):
        MALE = 'male', 'ذكر'
        FEMALE = 'female', 'أنثى'

    # ── بيانات أساسية ───────────────────────────────────────────
    name = models.CharField("الاسم", max_length=200)
    gender = models.CharField(
        "الجنس", max_length=10, choices=Gender.choices, default=Gender.MALE, blank=True
    )
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
    administration = models.ForeignKey(
        'setup.Administration', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="الإدارة",
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
    medical_insurance_expiry_date = models.DateField(
        "تاريخ انتهاء التأمين الطبي", null=True, blank=True,
        help_text="تاريخ تجديد بوليصة التأمين الصحي للموظف (وليس جدول نوع التأمين في الإعدادات).",
    )
    contract_expiry_date = models.DateField(
        "تاريخ انتهاء العقد", null=True, blank=True,
        help_text="تاريخ نهاية العقد المخطط — منفصل عن «تاريخ التوقف» عند التصفية الفعلية.",
    )

    class ContractType(models.TextChoices):
        FIXED = 'fixed', 'محدد المدة'
        UNLIMITED = 'unlimited', 'غير محدد المدة'

    contract_type = models.CharField(
        "نوع العقد", max_length=20,
        choices=ContractType.choices, blank=True, default='',
        help_text="محدد أو غير محدد المدة — يُحدَّث تلقائياً للسعودي بعد 3 سنوات.",
    )
    contract_start_date = models.DateField("تاريخ بداية العقد", null=True, blank=True)
    contract_duration_months = models.PositiveSmallIntegerField(
        "مدة العقد (أشهر)", null=True, blank=True,
        help_text="للسعودي: حد أقصى 12 شهراً.",
    )
    contract_duration_text = models.CharField(
        "مدة العقد (نص)", max_length=100, blank=True,
        help_text="للأجنبي: مثال «سنتان» أو «24 شهر».",
    )
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
    meal_allowance = models.DecimalField(
        "بدل التغذية", max_digits=12, decimal_places=2, default=0,
        help_text="يُضاف لإجمالي الراتب والمسير، ولا يُحتسب ضمن مكافأة نهاية الخدمة.",
    )
    insurance_deduction_rate = models.DecimalField(
        "نسبة خصم التأمينات", max_digits=5, decimal_places=2, default=0
    )
    bank = models.ForeignKey(
        'setup.Bank', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name="البنك"
    )
    iban = models.CharField("رقم الآيبان", max_length=34, blank=True)

    # ── الإجازات ───────────────────────────────────────────────
    # ⚠️ هذا الحقل يُراكم الأيام *المأخوذة* (المستهلكة) وليس المتوفرة.
    # التسمية القديمة 'available_leave_balance' أُبقيت للتوافق مع DB/الكود القائم.
    available_leave_balance = models.DecimalField(
        "أيام الإجازة المستخدمة", max_digits=8, decimal_places=2, default=0,
        help_text="عدد أيام الإجازات السنوية المأخوذة فعلياً — يزداد مع كل إجازة معتمدة. "
                  "الرصيد المتبقي = المستحق − هذا الحقل."
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
        """إجمالي الراتب الشهري (يشمل بدل التغذية)."""
        return (
            self.basic_salary + self.housing_allowance + self.transport_allowance
            + self.other_allowance + self.cash_amount + self.meal_allowance
        )

    @property
    def salary_for_end_of_service(self):
        """أساس احتساب مكافأة نهاية الخدمة — بدون بدل التغذية."""
        return (
            self.basic_salary + self.housing_allowance + self.transport_allowance
            + self.other_allowance + self.cash_amount
        )

    @property
    def contract_bank_transfer_amount(self):
        """مبلغ التحويل البنكي من العقد — كامل الإجمالي إن وُجدت كفالة."""
        from apps.employees.services.salary_payment import contract_bank_transfer_amount
        return contract_bank_transfer_amount(self)

    @property
    def payroll_salary_mode_label(self):
        from apps.employees.services.salary_payment import payroll_salary_mode_label
        return payroll_salary_mode_label(self)

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
        """الأجر اليومي = إجمالي الراتب ÷ 30 (قاعدة الشهر الموحدة)."""
        from apps.core.salary_month import daily_rate_from_total
        return daily_rate_from_total(self.total_salary)

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
        PENALTY = 'penalty', 'مخالفة (خصم مالي)'
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

    # ── حقول الخصم (للنوع PENALTY) ──
    deduction_amount = models.DecimalField(
        "مبلغ الخصم", max_digits=12, decimal_places=2, default=0,
        help_text="يُطبَّق فقط عند النوع 'مخالفة' ويظهر تلقائياً في المسير الشهري"
    )
    applied_to_payroll = models.ForeignKey(
        'payroll.PayrollRun', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='consumed_penalties', verbose_name="المسير المُحتسب فيه"
    )
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
            'penalty': 'PEN',
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
    applied_to_payroll = models.ForeignKey(
        'payroll.PayrollRun', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='consumed_unpaid_leaves',
        verbose_name="المسير المُحتسب فيه (للإجازات بدون راتب)"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "إجازة موظف"
        verbose_name_plural = "إجازات الموظفين"
        ordering = ['-date_from', '-created_at']

    def __str__(self):
        return f"{self.employee.name} — {self.get_leave_type_display()} ({self.date_from} → {self.date_to})"


# ══════════════════════════════════════════════════════════════════════════════
# عهدة موظف (استلام / تصفية)
# ══════════════════════════════════════════════════════════════════════════════
class EmployeeCustody(BaseModel):
    """عهدة من ممتلكات الشركة بحوزة الموظف (لابتوب، جوال، مفاتيح…)"""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'بالحوزة'
        RETURNED = 'returned', 'مُعادة'

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='custodies',
        verbose_name="الموظف"
    )
    serial_number = models.CharField(
        "الرقم المتسلسل", max_length=40, blank=True, db_index=True,
        help_text="مثال: CR-260512-0005-A3F2"
    )
    item_name = models.CharField("اسم العهدة", max_length=200)
    item_details = models.TextField("التفاصيل (موديل/سيريال)", blank=True)
    quantity = models.PositiveIntegerField("الكمية", default=1)
    estimated_value = models.DecimalField(
        "القيمة التقديرية", max_digits=12, decimal_places=2, null=True, blank=True
    )
    received_at = models.DateField("تاريخ الاستلام")
    notes = models.TextField("ملاحظات", blank=True)
    document = models.FileField(
        "مستند الاستلام", upload_to='employees/custody/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    status = models.CharField(
        "الحالة", max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    returned_at = models.DateField("تاريخ الإعادة", null=True, blank=True)
    return_notes = models.TextField("ملاحظات الإعادة", blank=True)
    return_document = models.FileField(
        "مستند التصفية", upload_to='employees/custody/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_custodies', verbose_name="أُضيفت بواسطة"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "عهدة موظف"
        verbose_name_plural = "عهد الموظفين"
        ordering = ['-received_at', '-created_at']

    def __str__(self):
        return f"{self.employee.name} — {self.item_name} ({self.get_status_display()})"


# ══════════════════════════════════════════════════════════════════════════════
# عرض وظيفي صادر للموظف
# ══════════════════════════════════════════════════════════════════════════════
class EmployeeJobOffer(BaseModel):
    """خطاب تعريف / عرض وظيفي صادر للموظف لجهة خارجية."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='job_offers',
        verbose_name="الموظف"
    )
    serial_number = models.CharField(
        "الرقم المتسلسل", max_length=40, blank=True, db_index=True,
        help_text="مثال: EL-260512-0005-A3F2"
    )
    addressed_to = models.CharField("الجهة المُوجَّه إليها", max_length=200)
    purpose = models.CharField("الغرض", max_length=300, blank=True)
    issued_at = models.DateField("تاريخ الإصدار")
    notes = models.TextField("ملاحظات", blank=True)
    document = models.FileField(
        "مستند مرفق", upload_to='employees/job_offers/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_job_offers', verbose_name="أُصدرت بواسطة"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "عرض وظيفي"
        verbose_name_plural = "العروض الوظيفية"
        ordering = ['-issued_at', '-created_at']

    def __str__(self):
        return f"{self.employee.name} — {self.addressed_to} ({self.issued_at})"


# ══════════════════════════════════════════════════════════════════════════════
# رحلة عمل
# ══════════════════════════════════════════════════════════════════════════════
class EmployeeBusinessTrip(BaseModel):
    """مهمة / رحلة عمل رسمية للموظف."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='business_trips',
        verbose_name="الموظف"
    )
    serial_number = models.CharField(
        "الرقم المتسلسل", max_length=40, blank=True, db_index=True,
        help_text="مثال: BT-260512-0005-A3F2"
    )
    destination = models.CharField("الوجهة", max_length=200)
    purpose = models.CharField("الغرض", max_length=300)
    start_date = models.DateField("من تاريخ")
    end_date = models.DateField("إلى تاريخ")
    estimated_cost = models.DecimalField(
        "التكلفة التقديرية", max_digits=12, decimal_places=2, null=True, blank=True
    )
    notes = models.TextField("ملاحظات", blank=True)
    document = models.FileField(
        "مستند مرفق", upload_to='employees/business_trips/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_business_trips', verbose_name="أُضيفت بواسطة"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "رحلة عمل"
        verbose_name_plural = "رحلات العمل"
        ordering = ['-start_date', '-created_at']

    def __str__(self):
        return f"{self.employee.name} — {self.destination} ({self.start_date} → {self.end_date})"

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1


# ══════════════════════════════════════════════════════════════════════════════
# سلفة موظف
# ══════════════════════════════════════════════════════════════════════════════
class EmployeeLoan(BaseModel):
    """سلفة مالية ممنوحة للموظف، تُسدَّد على دفعات شهرية."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'قيد السداد'
        PAID = 'paid', 'مُسدَّدة'
        CANCELLED = 'cancelled', 'مُلغاة'

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='loans',
        verbose_name="الموظف"
    )
    serial_number = models.CharField(
        "الرقم المتسلسل", max_length=40, blank=True, db_index=True,
        help_text="مثال: LN-260512-0005-A3F2"
    )
    amount = models.DecimalField(
        "مبلغ السلفة", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    monthly_deduction = models.DecimalField(
        "الخصم الشهري", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    installments = models.PositiveIntegerField("عدد الأقساط", default=1)
    reason = models.CharField("سبب السلفة", max_length=300, blank=True)
    issued_at = models.DateField("تاريخ الصرف")
    first_deduction_date = models.DateField("تاريخ بداية الخصم", null=True, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    document = models.FileField(
        "مستند مرفق", upload_to='employees/loans/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    status = models.CharField(
        "الحالة", max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_loans', verbose_name="أُضيفت بواسطة"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "سلفة موظف"
        verbose_name_plural = "سلف الموظفين"
        ordering = ['-issued_at', '-created_at']

    def __str__(self):
        return f"{self.employee.name} — {self.amount} ({self.get_status_display()})"

    @property
    def remaining_balance(self):
        """الرصيد المتبقي = المبلغ - مجموع الأقساط المحصّلة فعلياً."""
        from decimal import Decimal
        paid = self.installments_log.filter(status='paid').aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        return (Decimal(self.amount) - Decimal(paid)).quantize(Decimal('0.01'))

    def generate_installments(self):
        """يولّد سجلات LoanInstallment حسب عدد الأقساط وتاريخ بداية الخصم."""
        from decimal import Decimal
        from datetime import date
        if self.installments_log.exists():
            return  # موجودة بالفعل
        first = self.first_deduction_date or self.issued_at
        n = max(1, int(self.installments or 1))
        total_loan = Decimal(self.amount)
        per = Decimal(self.monthly_deduction)
        from calendar import monthrange
        y, m = first.year, first.month
        for i in range(n):
            if i == n - 1:
                installment_amount = (
                    total_loan - per * Decimal(n - 1)
                ).quantize(Decimal('0.01'))
            else:
                installment_amount = per
            # تاريخ القسط: نفس يوم الشهر الأول، أو آخر يوم في الشهر إن لم يوجد
            try:
                due = date(y, m, first.day)
            except ValueError:
                last_day = monthrange(y, m)[1]
                due = date(y, m, last_day)
            LoanInstallment.objects.create(
                loan=self,
                period_year=y, period_month=m,
                due_date=due,
                amount=installment_amount,
                status=LoanInstallment.Status.PENDING,
            )
            # تقدم شهراً
            m += 1
            if m > 12:
                m = 1
                y += 1


# ══════════════════════════════════════════════════════════════════════════════
# قسط سلفة (سجل شهري لكل قسط)
# ══════════════════════════════════════════════════════════════════════════════
class LoanInstallment(BaseModel):
    """قسط شهري واحد من سلفة. يُولَّد تلقائياً عند الموافقة على السلفة.

    يضمن idempotency للمسير: كل قسط يُحتسب في مسير واحد فقط.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'مستحق'
        PAID = 'paid', 'مُحصَّل'
        SKIPPED = 'skipped', 'مؤجَّل'
        CANCELLED = 'cancelled', 'ملغى'

    loan = models.ForeignKey(
        EmployeeLoan, on_delete=models.CASCADE, related_name='installments_log',
        verbose_name="السلفة"
    )
    period_year = models.PositiveIntegerField("السنة", db_index=True)
    period_month = models.PositiveSmallIntegerField("الشهر", db_index=True)
    due_date = models.DateField("تاريخ الاستحقاق")
    amount = models.DecimalField("المبلغ", max_digits=12, decimal_places=2)
    status = models.CharField(
        "الحالة", max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    applied_to_payroll = models.ForeignKey(
        'payroll.PayrollRun', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='consumed_loan_installments', verbose_name="المسير المُحتسب فيه"
    )
    notes = models.TextField("ملاحظات", blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "قسط سلفة"
        verbose_name_plural = "أقساط السلف"
        ordering = ['period_year', 'period_month']
        unique_together = [('loan', 'period_year', 'period_month')]

    def __str__(self):
        return f"{self.loan.employee.name} — {self.period_year}/{self.period_month:02d} = {self.amount}"


# ══════════════════════════════════════════════════════════════════════════════
# غياب موظف (يخصم من الراتب)
# ══════════════════════════════════════════════════════════════════════════════
class EmployeeAbsence(BaseModel):
    """تسجيل غياب يوم/أيام مع خصم تلقائي (إجمالي الراتب ÷ 30 يوماً)."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='absences',
        verbose_name="الموظف"
    )
    serial_number = models.CharField(
        "الرقم المتسلسل", max_length=40, blank=True, db_index=True,
        help_text="مثال: AB-260512-0005-A3F2"
    )
    absence_date = models.DateField("تاريخ الغياب", db_index=True)
    days = models.PositiveIntegerField(
        "عدد أيام الغياب", default=1,
        validators=[MinValueValidator(1)]
    )
    month_days = models.PositiveIntegerField(
        "أيام الشهر", default=30,
        help_text="أيام الشهر للحساب (ثابت 30) — لقطة عند الإنشاء"
    )
    total_salary_snapshot = models.DecimalField(
        "إجمالي الراتب وقت الغياب", max_digits=12, decimal_places=2, default=0
    )
    daily_rate = models.DecimalField(
        "سعر اليوم (محسوب)", max_digits=12, decimal_places=2, default=0,
        help_text="إجمالي الراتب ÷ 30"
    )
    deduction_amount = models.DecimalField(
        "إجمالي الخصم", max_digits=12, decimal_places=2, default=0,
        help_text="سعر اليوم × عدد أيام الغياب"
    )
    reason = models.CharField("سبب الغياب", max_length=300, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    document = models.FileField(
        "مستند مرفق", upload_to='employees/absences/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_absences', verbose_name="أُضيف بواسطة"
    )
    applied_to_payroll = models.ForeignKey(
        'payroll.PayrollRun', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='consumed_absences', verbose_name="المسير المُحتسب فيه"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "غياب موظف"
        verbose_name_plural = "غيابات الموظفين"
        ordering = ['-absence_date', '-created_at']

    def save(self, *args, **kwargs):
        from apps.core.salary_month import STANDARD_MONTH_DAYS, daily_rate_from_total

        self.month_days = STANDARD_MONTH_DAYS
        salary = Decimal(self.total_salary_snapshot or 0)
        if not salary and self.employee_id:
            salary = Decimal(self.employee.total_salary or 0)
        self.total_salary_snapshot = salary
        self.daily_rate = daily_rate_from_total(salary)
        self.deduction_amount = (
            self.daily_rate * Decimal(self.days or 0)
        ).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.name} — {self.absence_date} ({self.days} يوم)"


# ══════════════════════════════════════════════════════════════════════════════
# سجل الأرصدة والمخصصات الشهرية (Ledger for Leaves and EOSB)
# ══════════════════════════════════════════════════════════════════════════════
class EmployeeLedger(BaseModel):
    """
    سجل مالي تراكمي لكل موظف يحسب رصيد الإجازات ومكافأة نهاية الخدمة.
    يُضاف سطر تلقائياً عند اعتماد كل مسير رواتب، أو عند خصم إجازة، أو التصفية.
    """
    class TransactionType(models.TextChoices):
        INITIAL_BALANCE = 'initial', 'رصيد افتتاحي (من المباشرة وحتى الآن)'
        MONTHLY_PAYROLL = 'monthly', 'مخصص شهري (مسير رواتب)'
        LEAVE_TAKEN = 'leave_taken', 'استخدام رصيد إجازة (خصم)'
        FINAL_SETTLEMENT = 'settlement', 'تصفية نهائية (تصفير)'
        MANUAL_ADJUSTMENT = 'adjustment', 'تسوية يدوية'

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='accruals_ledger',
        verbose_name="الموظف"
    )
    transaction_type = models.CharField(
        "نوع الحركة", max_length=20, choices=TransactionType.choices,
        default=TransactionType.MONTHLY_PAYROLL
    )
    date = models.DateField("تاريخ الحركة", default=timezone.now)

    # ── التغييرات في هذه الحركة (Change) ──
    leave_days_change = models.DecimalField("التغير في أيام الإجازة", max_digits=8, decimal_places=4, default=0)
    leave_amount_change = models.DecimalField("التغير في قيمة الإجازة", max_digits=12, decimal_places=2, default=0)
    eosb_amount_change = models.DecimalField("التغير في قيمة نهاية الخدمة", max_digits=12, decimal_places=2, default=0)

    # ── الرصيد المتراكم بعد هذه الحركة (Cumulative Balance) ──
    cumulative_leave_days = models.DecimalField("رصيد أيام الإجازة المتراكم", max_digits=8, decimal_places=4, default=0)
    cumulative_leave_amount = models.DecimalField("رصيد قيمة الإجازة المتراكم", max_digits=12, decimal_places=2, default=0)
    cumulative_eosb_amount = models.DecimalField("رصيد نهاية الخدمة المتراكم", max_digits=12, decimal_places=2, default=0)

    # ── المرجع (Reference) ──
    payroll_run = models.ForeignKey(
        'payroll.PayrollRun', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ledger_entries', verbose_name="مسير الرواتب المرتبط"
    )
    notes = models.TextField("ملاحظات / تفاصيل الحساب", blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="أُضيفت بواسطة"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "سجل مخصصات موظف"
        verbose_name_plural = "سجلات مخصصات الموظفين"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.employee.name} — {self.get_transaction_type_display()} ({self.date})"

    @property
    def calculation_notes_display(self) -> str:
        """تفاصيل تقنية للعرض (يُعاد بناؤها للسجلات القديمة ذات ملاحظات قصيرة)."""
        from apps.employees.services.accrual_ledger_notes import display_ledger_notes
        return display_ledger_notes(self)

    @property
    def calculation_display_context(self) -> dict:
        """هيكل منظم لنافذة تفاصيل العملية الحسابية."""
        from apps.employees.services.accrual_ledger_notes import get_ledger_display_context
        return get_ledger_display_context(self)


