"""نماذج إدارة الصيانة — مهن، عمال، طلبات."""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.core.validators import IMAGE_VALIDATORS


class MaintenanceTrade(BaseModel):
    """مهنة صيانة (كهربائي، سباك، تكييف…)."""

    code = models.CharField('رمز المهنة', max_length=20, unique=True)
    name = models.CharField('اسم المهنة', max_length=100)
    is_active = models.BooleanField('نشط', default=True)

    class Meta:
        verbose_name = 'مهنة صيانة'
        verbose_name_plural = 'مهن الصيانة'
        ordering = ['name']

    def __str__(self):
        return self.name


class MaintenanceAsset(BaseModel):
    """أصل/معدّة صيانة (تكييف، ثلاجة، مصعد…)."""

    code = models.CharField('رمز الأصل', max_length=20, unique=True)
    name = models.CharField('اسم الأصل', max_length=150)
    is_active = models.BooleanField('نشط', default=True)

    class Meta:
        verbose_name = 'أصل صيانة'
        verbose_name_plural = 'أصول الصيانة'
        ordering = ['name']

    def __str__(self):
        return self.name


class MaintenanceWorker(BaseModel):
    """عامل صيانة — موظف نظام أو عامل خارجي."""

    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_worker_profiles',
        verbose_name='موظف مرتبط',
    )
    name = models.CharField('الاسم', max_length=200, blank=True)
    phone = models.CharField('رقم الجوال', max_length=20, blank=True)
    trade = models.ForeignKey(
        MaintenanceTrade,
        on_delete=models.PROTECT,
        related_name='workers',
        verbose_name='المهنة',
    )
    is_active = models.BooleanField('نشط', default=True)

    class Meta:
        verbose_name = 'عامل صيانة'
        verbose_name_plural = 'عمال الصيانة'
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active', 'is_deleted']),
        ]

    def __str__(self):
        return self.effective_name or f'عامل #{self.pk}'

    @property
    def effective_name(self) -> str:
        if self.name and self.name.strip():
            return self.name.strip()
        emp = self.employee
        if emp:
            return (emp.name or '').strip()
        return ''

    @property
    def effective_phone(self) -> str:
        if self.phone and self.phone.strip():
            return self.phone.strip()
        emp = self.employee
        if emp and (emp.phone or '').strip():
            return emp.phone.strip()
        return ''


class MaintenanceRequest(BaseModel):
    """طلب صيانة من فرع — سير: pending → assigned → worker_reported → manager_closed → branch_confirmed."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'بانتظار الإسناد'
        ASSIGNED = 'assigned', 'عند العامل'
        WORKER_REPORTED = 'worker_reported', 'بانتظار إغلاق مدير الصيانة'
        MANAGER_CLOSED = 'manager_closed', 'بانتظار تأكيد الفرع'
        BRANCH_CONFIRMED = 'branch_confirmed', 'مكتمل'
        RETURNED = 'returned', 'مرتجع'

    class Priority(models.TextChoices):
        NORMAL = 'normal', 'عادي'
        URGENT = 'urgent', 'عاجل'

    branch = models.ForeignKey(
        'core.Branch',
        on_delete=models.PROTECT,
        related_name='maintenance_requests',
        verbose_name='الفرع',
    )
    asset = models.ForeignKey(
        MaintenanceAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requests',
        verbose_name='الأصل',
    )
    title = models.CharField('عنوان الطلب', max_length=200)
    description = models.TextField('وصف المشكلة')
    location = models.CharField('الموقع', max_length=300, blank=True)
    priority = models.CharField(
        'الأولوية',
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    attachment = models.FileField(
        'مرفق',
        upload_to='maintenance/requests/%Y/%m/',
        blank=True,
        validators=IMAGE_VALIDATORS,
    )
    status = models.CharField(
        'الحالة',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='maintenance_requests_created',
        verbose_name='مُقدّم الطلب',
    )
    requested_at = models.DateTimeField('تاريخ الطلب', auto_now_add=True)

    assigned_worker = models.ForeignKey(
        MaintenanceWorker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_requests',
        verbose_name='العامل المُسند',
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_requests_assigned',
        verbose_name='أُسند بواسطة',
    )
    assigned_at = models.DateTimeField('تاريخ الإسناد', null=True, blank=True)

    worker_report_notes = models.TextField('ملاحظات العامل', blank=True)
    worker_reported_at = models.DateTimeField('تاريخ بلاغ العامل', null=True, blank=True)
    worker_report_token = models.CharField('رمز بلاغ العامل', max_length=64, blank=True, db_index=True)

    manager_closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_requests_closed',
        verbose_name='أُغلق بواسطة',
    )
    manager_closed_at = models.DateTimeField('تاريخ إغلاق المدير', null=True, blank=True)
    manager_notes = models.TextField('ملاحظات مدير الصيانة', blank=True)

    branch_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_requests_confirmed',
        verbose_name='أُكد بواسطة',
    )
    branch_confirmed_at = models.DateTimeField('تاريخ تأكيد الفرع', null=True, blank=True)

    return_notes = models.TextField('ملاحظات الإرجاع', blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_requests_returned',
        verbose_name='أُرجع بواسطة',
    )
    returned_at = models.DateTimeField('تاريخ الإرجاع', null=True, blank=True)
    resubmit_count = models.PositiveIntegerField('عدد إعادة التقديم', default=0)

    class Meta:
        verbose_name = 'طلب صيانة'
        verbose_name_plural = 'طلبات الصيانة'
        ordering = ['-requested_at', '-id']
        indexes = [
            models.Index(fields=['branch', 'status']),
            models.Index(fields=['requested_by', 'status']),
            models.Index(fields=['assigned_worker', 'status']),
        ]

    def __str__(self):
        return f'#{self.pk} — {self.title}'
