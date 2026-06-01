"""
النظام الأساسي - Core Models
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.core.validators import DOCUMENT_VALIDATORS, IMAGE_VALIDATORS

# ══════════════════════════════════════════════════════════════════════════════
# أدوات الـ Soft Delete
# ══════════════════════════════════════════════════════════════════════════════
class SoftDeleteQuerySet(models.QuerySet):
    """إدارة الحذف الوهمي (إخفاء السجلات بدلاً من مسحها فعلياً من قاعدة البيانات)"""
    def delete(self):
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

    def active(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)

class SoftDeleteManager(models.Manager):
    """دعم الـ Manager بالـ SoftDeleteQuerySet"""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)
    
    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db)

class BaseModel(models.Model):
    """
    النموذج الأب (Base Model) الذي يجب أن ترث منه جميع نماذج النظام السابقة والقادمة:
    - يوفر تاريخ الإنشاء والتحديث
    - يدعم الـ Soft Delete الافتراضي
    """
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)
    
    is_deleted = models.BooleanField("محذوف", default=False, db_index=True)
    deleted_at = models.DateTimeField("تاريخ الحذف", null=True, blank=True)

    # مدير الاستعلامات
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])

# ══════════════════════════════════════════════════════════════════════════════
# الشركة المركزية
# ══════════════════════════════════════════════════════════════════════════════
class Company(BaseModel):
    """المنشأة الأم (مبني على نظام Single-tenant، شركة واحدة بعدة فروع)"""
    name = models.CharField("اسم الشركة", max_length=200)
    tax_number = models.CharField("الرقم الضريبي", max_length=50, blank=True)
    commercial_record = models.CharField("السجل التجاري", max_length=50, blank=True)
    logo = models.ImageField("شعار الشركة", upload_to='company/logos/', blank=True, validators=IMAGE_VALIDATORS)
    contact_email = models.EmailField("البريد الإلكتروني", blank=True)
    contact_phone = models.CharField("رقم التواصل", max_length=20, blank=True)
    address = models.TextField("العنوان", blank=True)

    # تفعيل سجل التدقيق لالتقاط التغيرات (Audit Log)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "شركة"
        verbose_name_plural = "الشركات"

    def __str__(self):
        return self.name


# ══════════════════════════════════════════════════════════════════════════════
# الفروع
# ══════════════════════════════════════════════════════════════════════════════
class Branch(BaseModel):
    """فرع من فروع الشركة"""
    name = models.CharField("اسم الفرع", max_length=200)
    code = models.CharField("رمز الفرع", max_length=20, unique=True, help_text="رمز مختصر للفرع")
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        verbose_name="الشركة",
        related_name="branches"
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name="مدير الفرع",
        related_name="managed_branches",
        null=True,
        blank=True,
        help_text="المدير المسؤول عن هذا الفرع"
    )
    address = models.TextField("العنوان", blank=True)
    phone = models.CharField("رقم الهاتف", max_length=20, blank=True)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    is_active = models.BooleanField("نشط", default=True)
    
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "فرع"
        verbose_name_plural = "الفروع"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    @property
    def employees_count(self):
        """عدد الموظفين في هذا الفرع"""
        return self.employees.filter(is_deleted=False).count()
    
    @property
    def active_employees_count(self):
        """عدد الموظفين النشطين في هذا الفرع"""
        return self.employees.filter(is_deleted=False, user__is_active=True).count()

# ══════════════════════════════════════════════════════════════════════════════
# الأدوار - Role Based Access Control مبسط
# ══════════════════════════════════════════════════════════════════════════════
class AppModule(BaseModel):
    """وحدة (نظام فرعي) في التطبيق — مثل الموظفين، الفروع، الأقسام..."""
    code = models.CharField("الرمز", max_length=50, unique=True, help_text="مثل: employees, branches")
    name = models.CharField("الاسم", max_length=100)
    icon = models.CharField("الأيقونة", max_length=50, default='package', help_text="اسم أيقونة Lucide")
    order = models.IntegerField("الترتيب", default=0)
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "وحدة"
        verbose_name_plural = "الوحدات"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Permission(BaseModel):
    """صلاحية محددة = وحدة + عملية (view/add/edit/delete)"""

    class Operation(models.TextChoices):
        VIEW = 'view', 'عرض'
        ADD = 'add', 'إضافة'
        EDIT = 'edit', 'تعديل'
        DELETE = 'delete', 'حذف'
        APPROVE_BRANCH = 'approve_branch', 'موافقة الفرع'
        APPROVE_GM = 'approve_gm', 'موافقة المدير العام'
        APPROVE_OFFICER = 'approve_officer', 'تنفيذ موظف الموارد'
        RETURN = 'return', 'إرجاع'
        RESUBMIT = 'resubmit', 'إعادة إرسال'

    module = models.ForeignKey(
        AppModule,
        on_delete=models.CASCADE,
        verbose_name="الوحدة",
        related_name="permissions"
    )
    operation = models.CharField(
        "العملية",
        max_length=20,
        choices=Operation.choices,
    )
    code = models.CharField("الرمز", max_length=100, unique=True, help_text="مثل: employees.view")
    name = models.CharField("الاسم", max_length=200)
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "صلاحية"
        verbose_name_plural = "الصلاحيات"
        ordering = ['module__order', 'operation']
        unique_together = [('module', 'operation')]

    def __str__(self):
        return self.name


class Role(BaseModel):
    """دور المستخدم - نظام RBAC مبسط"""
    
    class RoleType(models.TextChoices):
        ADMIN = 'admin', 'مدير النظام'
        HR_MANAGER = 'hr_manager', 'مدير موارد بشرية'
        HR_OFFICER = 'hr_officer', 'موظف موارد'
        MANAGER = 'manager', 'مدير قسم'
        SPECIALIST = 'specialist', 'أخصائي'
        EMPLOYEE = 'employee', 'موظف'
    
    name = models.CharField("اسم الدور", max_length=100, unique=True)
    role_type = models.CharField(
        "نوع الدور",
        max_length=20,
        choices=RoleType.choices,
        default=RoleType.EMPLOYEE
    )
    description = models.TextField("الوصف", blank=True)
    is_system_role = models.BooleanField("دور نظام", default=False, help_text="الأدوار الأساسية لا يمكن حذفها")
    is_active = models.BooleanField("نشط", default=True)

    permissions = models.ManyToManyField(
        Permission,
        verbose_name="الصلاحيات",
        related_name="roles",
        blank=True,
    )

    history = HistoricalRecords()  # تتبع الأمان للأدوار
    
    class Meta:
        verbose_name = "دور"
        verbose_name_plural = "الأدوار"
        ordering = ['name']

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # منع تعديل أنواع الأدوار الأساسية
        if self.pk and self.is_system_role:
            old_instance = Role.objects.filter(pk=self.pk).first()
            if old_instance:
                self.role_type = old_instance.role_type
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        if self.is_system_role:
            raise ValueError("لا يمكن حذف أدوار النظام")
        super().delete(*args, **kwargs)


class UserProfile(BaseModel):
    """ملف المستخدم الموسع"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="المستخدم",
        related_name="profile",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        verbose_name="الدور",
        related_name="users",
        null=True,
        blank=True
    )
    
    # ربط المستخدم بفرع معين
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        verbose_name="الفرع",
        related_name="employees",
        null=True,
        blank=True,
        help_text="الفرع الذي ينتمي له المستخدم"
    )
    
    # الفروع المخصصة للأخصائيين (يمكنهم الوصول لبيانات هذه الفروع)
    assigned_branches = models.ManyToManyField(
        Branch,
        verbose_name="الفروع المكلف بها",
        related_name="assigned_specialists",
        blank=True,
        help_text="الفروع التي يمكن للأخصائي الوصول إليها (يحددها مدير الموارد البشرية)"
    )
    
    user_number = models.CharField(
        "رقم المستخدم",
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text="رقم المستخدم للدخول"
    )
    phone = models.CharField("رقم الهاتف", max_length=20, blank=True)
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL,
        verbose_name="القسم",
        related_name="employees",
        null=True,
        blank=True,
        help_text="القسم الذي ينتمي له الموظف"
    )
    position = models.CharField("المنصب", max_length=100, blank=True)
    avatar = models.ImageField("الصورة الشخصية", upload_to="avatars/", blank=True, validators=IMAGE_VALIDATORS)
    is_protected = models.BooleanField("محمي", default=False, help_text="المستخدمين المحميين لا يمكن حذفهم أو تعديلهم")

    # صلاحيات على مستوى المستخدم (تعديل فوق صلاحيات الدور)
    extra_permissions = models.ManyToManyField(
        'Permission',
        related_name='extra_users',
        blank=True,
        verbose_name='صلاحيات إضافية',
        help_text='صلاحيات تُمنح لهذا المستخدم تحديداً بالإضافة إلى صلاحيات الدور'
    )
    denied_permissions = models.ManyToManyField(
        'Permission',
        related_name='denied_users',
        blank=True,
        verbose_name='صلاحيات مرفوضة',
        help_text='صلاحيات تُسحب من هذا المستخدم حتى لو كانت في الدور'
    )

    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "ملف مستخدم"
        verbose_name_plural = "ملفات المستخدمين"

    def __str__(self):
        return f"ملف {self.user.username}"
    
    def get_permissions(self):
        """صلاحيات فعلية للمستخدم = (صلاحيات الدور ∪ extra) − denied"""
        if not self.role:
            extra = set(self.extra_permissions.filter(is_active=True).values_list('code', flat=True)) if self.pk else set()
            denied = set(self.denied_permissions.filter(is_active=True).values_list('code', flat=True)) if self.pk else set()
            return list(extra - denied)
        role_perms = set(self.role.permissions.filter(is_active=True).values_list('code', flat=True))
        if self.pk:
            extra = set(self.extra_permissions.filter(is_active=True).values_list('code', flat=True))
            denied = set(self.denied_permissions.filter(is_active=True).values_list('code', flat=True))
        else:
            extra, denied = set(), set()
        return list((role_perms | extra) - denied)
    
    @property
    def role_type(self):
        if self.role:
            return self.role.role_type
        return None
    
    @property
    def is_admin(self):
        return self.role and self.role.role_type == Role.RoleType.ADMIN
    
    @property
    def is_hr_manager(self):
        """هل المستخدم مدير موارد بشرية؟"""
        return self.role and self.role.role_type == Role.RoleType.HR_MANAGER
    
    @property
    def is_manager(self):
        return self.role and self.role.role_type == Role.RoleType.MANAGER
    
    @property
    def is_specialist(self):
        """هل المستخدم أخصائي؟"""
        return self.role and self.role.role_type == Role.RoleType.SPECIALIST
    
    @property
    def is_employee(self):
        """هل المستخدم موظف عادي؟"""
        return self.role and self.role.role_type == Role.RoleType.EMPLOYEE
    
    def get_accessible_branches(self):
        """الفروع المتاحة — نفس منطق access_control (managed + branch + assigned)."""
        from apps.core.services.access_control import (
            filter_branches_queryset,
            get_accessible_branch_ids,
        )

        qs = Branch.objects.filter(is_deleted=False)
        branch_ids = get_accessible_branch_ids(self.user)
        if branch_ids is None:
            return qs
        return filter_branches_queryset(self.user, qs)
    
    def can_access_branch(self, branch):
        """هل يمكن للمستخدم الوصول لهذا الفرع؟"""
        from apps.core.services.access_control import get_accessible_branch_ids

        branch_ids = get_accessible_branch_ids(self.user)
        if branch_ids is None:
            return True
        return branch.id in branch_ids
    
    def can_manage_specialist_branches(self):
        """هل يمكن للمستخدم تعيين فروع للأخصائيين؟ (مدير الموارد البشرية فقط)"""
        return self.role and self.role.role_type == Role.RoleType.HR_MANAGER


# ══════════════════════════════════════════════════════════════════════════════
# طلبات العمليات السريعة المعلّقة (دورة موافقات متعددة المراحل)
# ══════════════════════════════════════════════════════════════════════════════
class PendingAction(BaseModel):
    """
    طلب عملية معلّق على موظف يمرّ بأربع مراحل قبل التنفيذ:
       1) الأخصائي ينشئ الطلب                       → pending_branch
       2) مدير الفرع يوافق                          → pending_gm
       3) المدير العام يوافق ويسند لموظف موارد       → pending_officer
       4) موظف الموارد يوافق فيُنفَّذ تلقائياً        → approved
    أي رفض في أي مرحلة يُعيد الطلب إلى الأخصائي بحالة returned مع ملاحظات،
    ويستطيع تعديله وإعادة إرساله ليبدأ من جديد من مدير الفرع.
    """

    class ActionType(models.TextChoices):
        LEAVE = 'leave', 'تقديم إجازة'
        TRANSFER = 'transfer', 'نقل'
        SALARY_ADJUST = 'salary_adjust', 'تعديل راتب'
        TERMINATE = 'terminate', 'إنهاء خدمة'
        REACTIVATE = 'reactivate', 'إعادة تنشيط'
        CUSTODY_RECEIVE = 'custody_receive', 'استلام عهدة'
        CUSTODY_CLEAR = 'custody_clear', 'تصفية عهدة'
        JOB_OFFER = 'job_offer', 'عرض وظيفي'
        BUSINESS_TRIP = 'business_trip', 'رحلة عمل'
        LOAN_REQUEST = 'loan_request', 'تقديم سلفة'
        ABSENCE = 'absence', 'تسجيل غياب'
        CONTRACT_END = 'contract_end', 'انتهاء عقد'
        END_OF_SERVICE = 'end_of_service', 'تصفية نهاية خدمة / استقالة'

    class Status(models.TextChoices):
        PENDING_BRANCH = 'pending_branch', 'بانتظار مدير الفرع'
        PENDING_GM = 'pending_gm', 'بانتظار المدير العام'
        PENDING_OFFICER = 'pending_officer', 'بانتظار موظف الموارد'
        APPROVED = 'approved', 'مُنفَّذ'
        RETURNED = 'returned', 'مُرتجَع للتعديل'

    class Stage(models.TextChoices):
        BRANCH = 'branch', 'مدير الفرع'
        GM = 'gm', 'المدير العام'
        OFFICER = 'officer', 'موظف الموارد'

    action_type = models.CharField(
        "نوع العملية", max_length=20, choices=ActionType.choices, db_index=True
    )
    status = models.CharField(
        "الحالة", max_length=20, choices=Status.choices,
        default=Status.PENDING_BRANCH, db_index=True
    )

    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE,
        related_name='pending_actions', verbose_name="الموظف"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pending_actions', verbose_name="الفرع",
        help_text="يُستخدم لتوجيه الطلب لمدير الفرع المسؤول"
    )

    # حمولة العملية كاملةً (الحقول التي أدخلها الأخصائي)
    payload = models.JSONField("بيانات العملية", default=dict, blank=True)
    attachment = models.FileField(
        "مرفق", upload_to='pending_actions/', null=True, blank=True,
        validators=DOCUMENT_VALIDATORS,
    )

    # ── تتبّع الإنشاء ──
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='requested_pending_actions', verbose_name="مقدّم الطلب"
    )
    requested_at = models.DateTimeField("تاريخ الطلب", auto_now_add=True)

    # ── المرحلة 1: مدير الفرع ──
    branch_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='branch_reviewed_actions', verbose_name="موافقة مدير الفرع"
    )
    branch_reviewed_at = models.DateTimeField("تاريخ موافقة مدير الفرع", null=True, blank=True)
    branch_notes = models.TextField("ملاحظات مدير الفرع", blank=True)

    # ── المرحلة 2: المدير العام ──
    gm_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gm_reviewed_actions', verbose_name="موافقة المدير العام"
    )
    gm_reviewed_at = models.DateTimeField("تاريخ موافقة المدير العام", null=True, blank=True)
    gm_notes = models.TextField("ملاحظات المدير العام", blank=True)

    # ── المرحلة 3: الإسناد لموظف موارد ──
    assigned_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_pending_actions', verbose_name="موظف الموارد المُعيَّن"
    )
    assigned_at = models.DateTimeField("تاريخ التعيين", null=True, blank=True)

    # ── المرحلة 4: موظف الموارد ──
    officer_reviewed_at = models.DateTimeField("تاريخ موافقة موظف الموارد", null=True, blank=True)
    officer_notes = models.TextField("ملاحظات موظف الموارد", blank=True)

    # ── الإرجاع للتعديل ──
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='returned_pending_actions', verbose_name="مَن أرجعه"
    )
    returned_at = models.DateTimeField("تاريخ الإرجاع", null=True, blank=True)
    returned_from_stage = models.CharField(
        "المرحلة التي رُجِع منها", max_length=10,
        choices=Stage.choices, blank=True, default=''
    )
    return_notes = models.TextField("ملاحظات الإرجاع", blank=True)
    resubmit_count = models.PositiveSmallIntegerField("عدد مرات إعادة الإرسال", default=0)

    # ── نتيجة التنفيذ بعد الموافقة النهائية ──
    executed_at = models.DateTimeField("تاريخ التنفيذ", null=True, blank=True)
    execution_error = models.TextField("خطأ التنفيذ", blank=True)

    # ── حقول قديمة (للتوافق فقط — لم تعد مستخدمة) ──
    # نُبقي reviewed_by / reviewed_at / review_notes كحقول مهجورة لتفادي data loss
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_pending_actions', verbose_name="(قديم) راجعها"
    )
    reviewed_at = models.DateTimeField("(قديم) تاريخ المراجعة", null=True, blank=True)
    review_notes = models.TextField("(قديم) ملاحظات المراجعة", blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "طلب عملية معلّق"
        verbose_name_plural = "طلبات العمليات المعلّقة"
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['status', '-requested_at']),
            models.Index(fields=['branch', 'status']),
            models.Index(fields=['assigned_officer', 'status']),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()} — {self.employee.name} ({self.get_status_display()})"

    # ── خصائص مساعدة ──
    @property
    def is_pending(self):
        return self.status in {
            self.Status.PENDING_BRANCH,
            self.Status.PENDING_GM,
            self.Status.PENDING_OFFICER,
        }

    @property
    def is_done(self):
        return self.status == self.Status.APPROVED

    @property
    def current_stage(self):
        """يُرجع الجهة المنتظَر منها الإجراء حالياً (Stage) أو None."""
        mapping = {
            self.Status.PENDING_BRANCH: self.Stage.BRANCH,
            self.Status.PENDING_GM: self.Stage.GM,
            self.Status.PENDING_OFFICER: self.Stage.OFFICER,
        }
        return mapping.get(self.status)


# ══════════════════════════════════════════════════════════════════════════════
# الإشعارات الداخلية (الجرس)
# ══════════════════════════════════════════════════════════════════════════════
class Notification(BaseModel):
    """إشعار داخل النظام يظهر للمستخدم في قائمة الجرس."""

    class Color(models.TextChoices):
        PRIMARY = 'primary', 'أزرق'
        EMERALD = 'emerald', 'أخضر'
        AMBER = 'amber', 'برتقالي'
        RED = 'red', 'أحمر'
        INDIGO = 'indigo', 'بنفسجي'
        SLATE = 'slate', 'رمادي'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notifications', verbose_name="المستلم"
    )
    title = models.CharField("العنوان", max_length=200)
    message = models.TextField("الرسالة", blank=True)
    link = models.CharField("الرابط", max_length=300, blank=True)
    icon = models.CharField("الأيقونة", max_length=40, default='bell')
    color = models.CharField(
        "اللون", max_length=12, choices=Color.choices, default=Color.PRIMARY
    )
    is_read = models.BooleanField("مقروء", default=False, db_index=True)
    read_at = models.DateTimeField("وقت القراءة", null=True, blank=True)

    # ربط اختياري بطلب معلّق
    related_action = models.ForeignKey(
        PendingAction, on_delete=models.CASCADE, null=True, blank=True,
        related_name='notifications', verbose_name="الطلب المرتبط"
    )

    class Meta:
        verbose_name = "إشعار"
        verbose_name_plural = "الإشعارات"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"{self.recipient} — {self.title}"

    def mark_read(self):
        if not self.is_read:
            from django.utils import timezone
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


# ══════════════════════════════════════════════════════════════════════════════
# سجل عمليات النظام (أحداث لا يسجلها simple_history — مثل كلمة المرور)
# ══════════════════════════════════════════════════════════════════════════════
class SystemAuditLog(models.Model):
    """عمليات تشغيلية/أمنية بصياغة عربية تقنية."""

    class Action(models.TextChoices):
        PASSWORD_CHANGE_SELF = 'password_change_self', 'تغيير كلمة المرور (ذاتي)'
        PASSWORD_CHANGE_ADMIN = 'password_change_admin', 'تعيين كلمة مرور (مدير)'
        USER_LOGIN = 'user_login', 'تسجيل دخول'

    created_at = models.DateTimeField('الوقت', auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_audit_actions',
        verbose_name='المنفّذ',
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_audit_targets',
        verbose_name='المستخدم المستهدف',
    )
    action = models.CharField('رمز العملية', max_length=40, choices=Action.choices, db_index=True)
    summary = models.CharField('العملية', max_length=255)
    details = models.TextField('التفاصيل التقنية', blank=True)
    ip_address = models.GenericIPAddressField('عنوان IP', null=True, blank=True)

    class Meta:
        verbose_name = 'سجل عملية نظام'
        verbose_name_plural = 'سجل عمليات النظام'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} — {self.summary}'


# ══════════════════════════════════════════════════════════════════════════════
# سجل النسخ الاحتياطي لقاعدة البيانات (لوحة الإدارة + الداشبورد)
# ══════════════════════════════════════════════════════════════════════════════
class DatabaseBackupLog(models.Model):
    """سجل لكل محاولة نسخ احتياطي (يدوي أو مجدول)."""

    class Trigger(models.TextChoices):
        MANUAL = 'manual', 'يدوي'
        CRON = 'cron', 'مجدول (Cron)'
        MIGRATE = 'migrate', 'قبل المهاجرات'

    class Status(models.TextChoices):
        SUCCESS = 'success', 'نجاح كامل'
        PARTIAL = 'partial', 'نجاح جزئي (محلي — فشل الرفع لـ R2)'
        FAILED = 'failed', 'فشل'

    created_at = models.DateTimeField('وقت التنفيذ', auto_now_add=True, db_index=True)
    trigger = models.CharField(
        'المصدر', max_length=16, choices=Trigger.choices, default=Trigger.MANUAL, db_index=True
    )
    status = models.CharField('الحالة', max_length=16, choices=Status.choices, db_index=True)
    filename = models.CharField('اسم الملف', max_length=255)
    size_bytes = models.BigIntegerField('الحجم (بايت)', default=0)
    r2_key = models.CharField('مفتاح R2', max_length=512, blank=True)
    dump_error = models.TextField('خطأ النسخ', blank=True)
    r2_error = models.TextField('خطأ رفع R2', blank=True)

    class Meta:
        verbose_name = 'سجل نسخ احتياطي'
        verbose_name_plural = 'سجلات النسخ الاحتياطي'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} — {self.get_status_display()}'


