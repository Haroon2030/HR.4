"""أجهزة البصمة وسجلات الحضور."""
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, Branch


class BiometricDevice(BaseModel):
    """جهاز بصمة متصل بالشبكة (ZKTeco وما يشابهه)."""

    class DeviceType(models.TextChoices):
        ZKTECO = 'zkteco', 'ZKTeco / ZK'

    class ConnectionStatus(models.TextChoices):
        UNKNOWN = 'unknown', 'غير معروف'
        ONLINE = 'online', 'متصل'
        OFFLINE = 'offline', 'غير متصل'
        ERROR = 'error', 'خطأ'

    name = models.CharField('اسم الجهاز', max_length=120)
    device_type = models.CharField(
        'نوع الجهاز', max_length=20,
        choices=DeviceType.choices, default=DeviceType.ZKTECO,
    )
    ip_address = models.GenericIPAddressField('عنوان IP', protocol='IPv4')
    port = models.PositiveIntegerField('منفذ الاتصال', default=4370)
    comm_key = models.PositiveIntegerField(
        'كلمة اتصال الجهاز (Comm Key)', default=0,
        help_text='عادة 0 — راجع إعدادات الجهاز',
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='biometric_devices', verbose_name='الفرع',
    )
    serial_number = models.CharField('الرقم التسلسلي', max_length=64, blank=True)
    firmware_version = models.CharField('إصدار البرنامج', max_length=64, blank=True)
    is_active = models.BooleanField('نشط', default=True)
    connection_status = models.CharField(
        'حالة الاتصال', max_length=20,
        choices=ConnectionStatus.choices, default=ConnectionStatus.UNKNOWN,
    )
    last_sync_at = models.DateTimeField('آخر مزامنة', null=True, blank=True)
    last_ping_at = models.DateTimeField('آخر فحص اتصال', null=True, blank=True)
    last_error = models.TextField('آخر خطأ', blank=True)
    notes = models.TextField('ملاحظات', blank=True)
    agent_api_key = models.CharField(
        'مفتاح وكيل البصمة (مُجزّأ)',
        max_length=64,
        blank=True,
        default='',
        help_text='SHA-256 لمفتاح الوكيل المحلي — يُولَّد من لوحة الإدارة أو الأمر generate_attendance_agent_key',
    )

    class Meta:
        verbose_name = 'جهاز بصمة'
        verbose_name_plural = 'أجهزة البصمة'
        ordering = ['name']
        indexes = [
            models.Index(fields=['ip_address', 'port']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f'{self.name} ({self.ip_address}:{self.port})'

    @property
    def address_label(self) -> str:
        return f'{self.ip_address}:{self.port}'


class EmployeeBiometricEnrollment(BaseModel):
    """ربط موظف في النظام برقم مستخدم على جهاز البصمة."""

    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE,
        related_name='biometric_enrollments', verbose_name='الموظف',
    )
    device = models.ForeignKey(
        BiometricDevice, on_delete=models.CASCADE,
        related_name='enrollments', verbose_name='الجهاز',
    )
    device_user_id = models.PositiveIntegerField('رقم المستخدم على الجهاز', db_index=True)
    device_user_name = models.CharField('الاسم على الجهاز', max_length=200, blank=True)

    class Meta:
        verbose_name = 'تسجيل بصمة موظف'
        verbose_name_plural = 'تسجيلات البصمة'
        constraints = [
            models.UniqueConstraint(
                fields=['device', 'device_user_id'],
                condition=models.Q(is_deleted=False),
                name='uniq_device_user_per_device_active',
            ),
            models.UniqueConstraint(
                fields=['device', 'employee'],
                condition=models.Q(is_deleted=False),
                name='uniq_employee_per_device_active',
            ),
        ]

    def __str__(self):
        return f'{self.employee_id} → {self.device_user_id} على {self.device}'


class BiometricDeviceUser(BaseModel):
    """مستخدم مسجّل على جهاز البصمة (يُحدَّث عند سحب قائمة المستخدمين)."""

    device = models.ForeignKey(
        BiometricDevice, on_delete=models.CASCADE,
        related_name='device_users', verbose_name='الجهاز',
    )
    device_user_id = models.PositiveIntegerField('رقم المستخدم على الجهاز', db_index=True)
    name = models.CharField('الاسم على الجهاز', max_length=200, blank=True)
    card = models.CharField('رقم البطاقة', max_length=64, blank=True)
    privilege = models.PositiveSmallIntegerField('صلاحية الجهاز', null=True, blank=True)
    last_synced_at = models.DateTimeField('آخر سحب من الجهاز', null=True, blank=True)

    class Meta:
        verbose_name = 'مستخدم على جهاز البصمة'
        verbose_name_plural = 'مستخدمو أجهزة البصمة'
        ordering = ['device', 'device_user_id']
        constraints = [
            models.UniqueConstraint(
                fields=['device', 'device_user_id'],
                name='uniq_biometric_device_user',
            ),
        ]

    def __str__(self):
        label = self.name or f'مستخدم {self.device_user_id}'
        return f'{label} ({self.device_user_id})'


class AttendancePunch(BaseModel):
    """سجل حضور خام من الجهاز."""

    class PunchType(models.TextChoices):
        CHECK_IN = 'in', 'دخول'
        CHECK_OUT = 'out', 'خروج'
        BREAK_OUT = 'break_out', 'خروج استراحة'
        BREAK_IN = 'break_in', 'عودة استراحة'
        UNKNOWN = 'unknown', 'غير محدد'

    class PunchTypeSource(models.TextChoices):
        DEVICE = 'device', 'من الجهاز (status)'
        INFERRED = 'inferred', 'محسوب بالتسلسل'

    device = models.ForeignKey(
        BiometricDevice, on_delete=models.CASCADE,
        related_name='punches', verbose_name='الجهاز',
    )
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='attendance_punches',
        verbose_name='الموظف',
    )
    device_user_id = models.PositiveIntegerField('رقم المستخدم على الجهاز', db_index=True)
    device_user_name = models.CharField('الاسم على الجهاز', max_length=200, blank=True)
    punched_at = models.DateTimeField('وقت البصمة', db_index=True)
    punch_type = models.CharField(
        'نوع الحركة', max_length=20,
        choices=PunchType.choices, default=PunchType.UNKNOWN,
    )
    punch_type_source = models.CharField(
        'مصدر تصنيف الحركة', max_length=20,
        choices=PunchTypeSource.choices, default=PunchTypeSource.DEVICE,
        db_index=True,
    )
    verify_mode = models.PositiveSmallIntegerField('طريقة التحقق (رمز ZK)', null=True, blank=True)
    verify_mode_label = models.CharField('طريقة التحقق', max_length=40, blank=True)
    device_record_uid = models.PositiveIntegerField(
        'معرف السجل على الجهاز', null=True, blank=True,
        help_text='لمنع التكرار عند المزامنة',
    )
    raw_status = models.PositiveSmallIntegerField('حالة خام من الجهاز', null=True, blank=True)
    sync_batch = models.CharField('دفعة المزامنة', max_length=40, blank=True, db_index=True)

    class Meta:
        verbose_name = 'سجل بصمة'
        verbose_name_plural = 'سجلات البصمة'
        ordering = ['-punched_at']
        indexes = [
            models.Index(fields=['device', 'punched_at']),
            models.Index(fields=['employee', 'punched_at']),
            models.Index(fields=['is_deleted', 'punched_at'], name='att_punch_del_punched_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['device', 'device_record_uid'],
                condition=models.Q(device_record_uid__isnull=False),
                name='uniq_device_attendance_uid',
            ),
            models.UniqueConstraint(
                fields=['device', 'device_user_id', 'punched_at'],
                name='uniq_device_user_punch_time',
            ),
        ]

    def __str__(self):
        return f'{self.punched_at} — user {self.device_user_id}'

    @property
    def local_punched_at(self):
        return timezone.localtime(self.punched_at)

    def refresh_display_fields(self, name_map: dict[int, str] | None = None) -> None:
        from apps.attendance.services.labels import punch_type_for_status, verify_mode_label

        if name_map and not self.device_user_name:
            self.device_user_name = name_map.get(self.device_user_id, '')
        if self.raw_status is not None:
            code, label = punch_type_for_status(self.raw_status)
            if code in {c.value for c in self.PunchType}:
                self.punch_type = code
            self.verify_mode_label = verify_mode_label(self.verify_mode)
        elif not self.verify_mode_label:
            self.verify_mode_label = verify_mode_label(self.verify_mode)


class EmployeeBiometricSettings(BaseModel):
    """إعدادات عرض بصمات الموظف (وقت الدخول/الخروج وتجاهل التأخير)."""

    employee = models.OneToOneField(
        'employees.Employee', on_delete=models.CASCADE,
        related_name='biometric_settings', verbose_name='الموظف',
    )
    expected_check_in = models.TimeField(
        'وقت الدخول المتوقع', null=True, blank=True,
        help_text='بصمات الدخول بعد هذا الوقت + فترة السماح لا تُعرض في تبويب البصمة.',
    )
    expected_check_out = models.TimeField(
        'وقت الخروج المتوقع', null=True, blank=True,
        help_text='للمرجعية — يُستخدم لاحقاً في التقارير.',
    )
    late_grace_minutes = models.PositiveSmallIntegerField(
        'سماح التأخير (دقيقة)', default=30,
        help_text='بعد وقت الدخول + هذه الدقائق تُخفى بصمات الدخول المتأخرة.',
    )

    class Meta:
        verbose_name = 'إعدادات بصمة الموظف'
        verbose_name_plural = 'إعدادات بصمات الموظفين'

    def __str__(self):
        return f'بصمة — {self.employee_id}'

    @property
    def check_in_cutoff_label(self) -> str:
        if not self.expected_check_in:
            return ''
        from datetime import datetime, timedelta
        base = datetime.combine(datetime.today(), self.expected_check_in)
        end = (base + timedelta(minutes=self.late_grace_minutes or 30)).time()
        return f'{self.expected_check_in.strftime("%H:%M")} + {self.late_grace_minutes} د → {end.strftime("%H:%M")}'


class AttendanceIngestLog(BaseModel):
    """سجل تدقيق استقبال دفعات البصمات من الوكيل المحلي."""

    class Status(models.TextChoices):
        SUCCESS = 'success', 'نجاح'
        REJECTED_SIGNATURE = 'rejected_signature', 'توقيع مرفوض'
        REJECTED_PAYLOAD = 'rejected_payload', 'حمولة مرفوضة'
        ERROR = 'error', 'خطأ'

    device = models.ForeignKey(
        BiometricDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ingest_logs',
        verbose_name='الجهاز',
    )
    agent_id = models.CharField('معرّف الوكيل', max_length=120, blank=True, default='')
    status = models.CharField(
        'الحالة',
        max_length=32,
        choices=Status.choices,
        db_index=True,
    )
    signature_valid = models.BooleanField('توقيع صالح', null=True, blank=True)
    punches_received = models.PositiveIntegerField('بصمات مستلمة', default=0)
    imported = models.PositiveIntegerField('بصمات جديدة', default=0)
    skipped_duplicate = models.PositiveIntegerField('مكررة', default=0)
    skipped_time_filter = models.PositiveIntegerField('مرفوضة زمنياً', default=0)
    users_updated = models.PositiveIntegerField('مستخدمون محدّثون', default=0)
    message = models.TextField('رسالة', blank=True, default='')
    client_ip = models.GenericIPAddressField('عنوان IP', null=True, blank=True)
    user_agent = models.CharField('وكيل المستخدم', max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'سجل استقبال بصمات'
        verbose_name_plural = 'سجلات استقبال البصمات'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['device', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        device_label = self.device_id or '—'
        return f'ingest #{self.pk} — جهاز {device_label} — {self.status}'


class BiometricEnrollmentAuditLog(BaseModel):
    """تدقيق إعادة ربط موظف برقم مستخدم على جهاز البصمة."""

    class Action(models.TextChoices):
        CREATE = 'create', 'ربط جديد'
        REASSIGN = 'reassign', 'إعادة ربط'
        UPDATE = 'update', 'تحديث'

    device = models.ForeignKey(
        BiometricDevice,
        on_delete=models.CASCADE,
        related_name='enrollment_audit_logs',
        verbose_name='الجهاز',
    )
    device_user_id = models.PositiveIntegerField('رقم المستخدم على الجهاز', db_index=True)
    previous_employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_enrollment_replaced_audit',
        verbose_name='الموظف السابق',
    )
    new_employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='biometric_enrollment_audit',
        verbose_name='الموظف الجديد',
    )
    device_user_name = models.CharField('اسم المستخدم على الجهاز', max_length=120, blank=True, default='')
    action = models.CharField('الإجراء', max_length=16, choices=Action.choices)
    punches_relinked = models.PositiveIntegerField('بصمات أُعيد ربطها', default=0)
    performed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_enrollment_audits',
        verbose_name='نُفّذ بواسطة',
    )

    class Meta:
        verbose_name = 'تدقيق ربط بصمة'
        verbose_name_plural = 'تدقيق ربط البصمات'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'device_user_id', '-created_at']),
            models.Index(fields=['new_employee', '-created_at']),
        ]

    def __str__(self):
        return (
            f'ربط جهاز {self.device_id} — مستخدم {self.device_user_id} '
            f'→ موظف {self.new_employee_id} ({self.action})'
        )


class BiometricPullRequest(BaseModel):
    """طلب سحب من لوحة HR — ينفّذه وكيل الفرع (يُخزَّن في DB وليس cache فقط)."""

    device = models.ForeignKey(
        BiometricDevice,
        on_delete=models.CASCADE,
        related_name='pull_requests',
        verbose_name='الجهاز',
    )
    requested_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biometric_pull_requests',
        verbose_name='طُلب بواسطة',
    )
    date_from = models.DateField('من تاريخ', null=True, blank=True)
    date_to = models.DateField('إلى تاريخ', null=True, blank=True)
    acknowledged_at = models.DateTimeField('تم التنفيذ', null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = 'طلب سحب بصمة'
        verbose_name_plural = 'طلبات سحب البصمة'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'acknowledged_at', '-created_at']),
        ]

    def __str__(self):
        state = 'مُنفَّذ' if self.acknowledged_at else 'معلّق'
        return f'سحب جهاز {self.device_id} — {state}'
