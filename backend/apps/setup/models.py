"""
موديلات جداول التهيئة (Lookups):
Nationality, Profession, Sponsorship, Insurance, InsuranceClass, SystemSettings.

تم نقلها من apps.core للحفاظ على فصل الأبعاد المعمارية.
الجداول الفعلية في DB ما زالت تحت أسماء `core_*` (للحفاظ على البيانات
القديمة)، ويتم ذلك عبر `Meta.db_table`.
"""
from datetime import time

from django.db import models
from django.conf import settings
from simple_history.models import HistoricalRecords

from apps.core.models import BaseModel
from apps.setup.operations_report_recipients import OPERATIONS_REPORT_RECIPIENT_ROLES


class SystemSettings(models.Model):
    """إعدادات النظام"""
    key = models.CharField("المفتاح", max_length=100, unique=True)
    value = models.TextField("القيمة")
    description = models.TextField("الوصف", blank=True)

    class Meta:
        db_table = 'core_systemsettings'
        verbose_name = "إعداد نظام"
        verbose_name_plural = "إعدادات النظام"

    def __str__(self):
        return self.key


class OperationsReportSettings(models.Model):
    """إعدادات تقرير العمليات اليومي (سجل واحد — pk=1)."""

    recipient_email = models.EmailField(
        'البريد المستلم (قديم)',
        blank=True,
        default='',
        help_text='للتوافق — يُزامَن من مدير النظام عند الحفظ.',
    )
    recipient_emails = models.JSONField(
        'بريد المستلمين حسب الدور',
        default=dict,
        blank=True,
        help_text='مفاتيح الأدوار: system_manager, hr_manager, ...',
    )
    recipient_phones = models.JSONField(
        'جوال واتساب حسب الدور',
        default=dict,
        blank=True,
        help_text='مفاتيح الأدوار: system_manager, hr_manager, ...',
    )
    send_via_whatsapp = models.BooleanField(
        'إرسال عبر واتساب',
        default=False,
        help_text='يرسل ملف PDF عبر WhatsApp (Evolution API) للأرقام المربوطة.',
    )
    is_enabled = models.BooleanField('تفعيل الإرسال التلقائي', default=False)
    send_time = models.TimeField(
        'وقت الإرسال',
        default=time(12, 0, 0),
        help_text='يُرسل يومياً عند هذا الوقت (توقيت Django — TIME_ZONE).',
    )
    include_pending = models.BooleanField('تضمين العمليات المعلّقة', default=True)
    include_completed = models.BooleanField('تضمين العمليات المُنجزة (يوم التقرير)', default=True)
    last_sent_at = models.DateTimeField('آخر إرسال', null=True, blank=True)
    updated_at = models.DateTimeField('آخر تحديث', auto_now=True)

    class Meta:
        db_table = 'setup_operationsreportsettings'
        verbose_name = 'إعدادات تقرير العمليات'
        verbose_name_plural = 'إعدادات تقرير العمليات'

    def __str__(self):
        return 'إعدادات تقرير العمليات'

    @classmethod
    def get_solo(cls) -> 'OperationsReportSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def recipient_emails_map(self) -> dict[str, str]:
        stored = dict(self.recipient_emails or {})
        if not any((v or '').strip() for v in stored.values()) and self.recipient_email:
            stored.setdefault('system_manager', self.recipient_email)
        return {
            key: (stored.get(key) or '').strip()
            for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES
        }

    def active_recipient_emails(self) -> list[str]:
        seen: set[str] = set()
        emails: list[str] = []
        for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES:
            addr = self.recipient_emails_map().get(key, '')
            if not addr:
                continue
            norm = addr.lower()
            if norm in seen:
                continue
            seen.add(norm)
            emails.append(addr)
        return emails

    def recipient_phones_map(self) -> dict[str, str]:
        stored = dict(self.recipient_phones or {})
        return {
            key: (stored.get(key) or '').strip()
            for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES
        }

    def active_recipient_phones(self) -> list[str]:
        seen: set[str] = set()
        phones: list[str] = []
        for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES:
            raw = self.recipient_phones_map().get(key, '')
            if not raw:
                continue
            norm = raw.replace(' ', '').replace('-', '')
            if norm in seen:
                continue
            seen.add(norm)
            phones.append(raw)
        return phones


class WorkflowWhatsAppSettings(models.Model):
    """إعدادات إشعارات واتساب لدورة الموافقات (سجل واحد — pk=1)."""

    is_enabled = models.BooleanField(
        'تفعيل إشعارات واتساب لسير العمل',
        default=True,
        help_text='يرسل تنبيهات عند رفع الطلبات ومراحل الموافقة.',
    )
    recipient_phones = models.JSONField(
        'جوال واتساب حسب الدور',
        default=dict,
        blank=True,
        help_text='مفاتيح: system_admin, hr_manager',
    )
    updated_at = models.DateTimeField('آخر تحديث', auto_now=True)

    class Meta:
        db_table = 'setup_workflowwhatsappsettings'
        verbose_name = 'إعدادات واتساب — سير العمل'
        verbose_name_plural = 'إعدادات واتساب — سير العمل'

    def __str__(self):
        return 'إعدادات واتساب — سير العمل'

    @classmethod
    def get_solo(cls) -> 'WorkflowWhatsAppSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def recipient_phones_map(self) -> dict[str, str]:
        from apps.setup.workflow_whatsapp_recipients import WORKFLOW_WHATSAPP_RECIPIENT_ROLES

        stored = dict(self.recipient_phones or {})
        return {
            key: (stored.get(key) or '').strip()
            for key, _ in WORKFLOW_WHATSAPP_RECIPIENT_ROLES
        }

    def phones_for_roles(self, *role_keys: str) -> list[str]:
        """أرقام فريدة للأدوار المطلوبة."""
        phone_map = self.recipient_phones_map()
        seen: set[str] = set()
        phones: list[str] = []
        for key in role_keys:
            raw = phone_map.get(key, '')
            if not raw:
                continue
            norm = raw.replace(' ', '').replace('-', '')
            if norm in seen:
                continue
            seen.add(norm)
            phones.append(raw)
        return phones


DEFAULT_EVOLUTION_WEBHOOK_EVENTS = [
    'QRCODE_UPDATED',
    'CONNECTION_UPDATE',
    'MESSAGES_UPSERT',
]


class EvolutionWhatsAppSettings(models.Model):
    """إعدادات ربط WhatsApp عبر Evolution API (سجل واحد — pk=1)."""

    class ConnectionStatus(models.TextChoices):
        UNKNOWN = 'unknown', 'غير معروف'
        OPEN = 'open', 'متصل'
        CLOSE = 'close', 'غير متصل'
        CONNECTING = 'connecting', 'جاري الربط'

    api_url = models.URLField(
        'رابط Evolution API',
        max_length=500,
        blank=True,
        default='',
        help_text='مثل http://72.61.107.230:8081',
    )
    api_key = models.CharField('مفتاح API', max_length=255, blank=True, default='')
    instance_name = models.CharField(
        'اسم Instance',
        max_length=64,
        blank=True,
        default='hr',
        help_text='اسم إنجليزي فقط — مثل hr أو main',
    )
    is_enabled = models.BooleanField('تفعيل إرسال WhatsApp', default=False)
    webhook_enabled = models.BooleanField('تفعيل Webhook', default=True)
    webhook_events = models.JSONField(
        'أحداث Webhook',
        default=list,
        blank=True,
        help_text='أحداث Evolution API المراد استقبالها.',
    )
    connection_status = models.CharField(
        'حالة الاتصال',
        max_length=20,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.UNKNOWN,
    )
    last_qrcode_base64 = models.TextField('آخر QR', blank=True, default='')
    last_webhook_at = models.DateTimeField('آخر Webhook', null=True, blank=True)
    last_status_sync_at = models.DateTimeField('آخر مزامنة حالة', null=True, blank=True)
    updated_at = models.DateTimeField('آخر تحديث', auto_now=True)

    class Meta:
        db_table = 'setup_evolutionwhatsappsettings'
        verbose_name = 'إعدادات WhatsApp (Evolution)'
        verbose_name_plural = 'إعدادات WhatsApp (Evolution)'

    def __str__(self):
        return 'إعدادات WhatsApp'

    @classmethod
    def get_solo(cls) -> 'EvolutionWhatsAppSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        if not obj.webhook_events:
            obj.webhook_events = list(DEFAULT_EVOLUTION_WEBHOOK_EVENTS)
            obj.save(update_fields=['webhook_events'])
        return obj

    def webhook_events_list(self) -> list[str]:
        events = self.webhook_events or DEFAULT_EVOLUTION_WEBHOOK_EVENTS
        return [str(e).strip().upper() for e in events if str(e).strip()]

    def api_key_masked(self) -> str:
        key = (self.api_key or '').strip()
        if not key:
            return ''
        if len(key) <= 4:
            return '••••'
        return f'{"•" * min(len(key) - 4, 12)}{key[-4:]}'

    def has_api_credentials(self) -> bool:
        return bool((self.api_url or '').strip() and (self.api_key or '').strip())

    def is_instance_valid(self) -> bool:
        import re
        name = (self.instance_name or '').strip()
        return bool(name and re.fullmatch(r'^[A-Za-z0-9._-]+$', name))


class Nationality(BaseModel):
    """الجنسيات"""
    code = models.CharField("رقم الجنسية", max_length=20, unique=True)
    name = models.CharField("اسم الجنسية", max_length=100)
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='core_historicalnationality')

    class Meta:
        db_table = 'core_nationality'
        verbose_name = "جنسية"
        verbose_name_plural = "الجنسيات"
        ordering = ['name']

    def __str__(self):
        return self.name


class Profession(BaseModel):
    """المهن"""
    code = models.CharField("رقم المهنة", max_length=20, unique=True)
    name = models.CharField("اسم المهنة", max_length=100)
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='core_historicalprofession')

    class Meta:
        db_table = 'core_profession'
        verbose_name = "مهنة"
        verbose_name_plural = "المهن"
        ordering = ['name']

    def __str__(self):
        return self.name


class Sponsorship(BaseModel):
    """الكفالات"""
    code = models.CharField("رقم الكفالة", max_length=20, unique=True)
    company_name = models.CharField("اسم الشركة", max_length=200)
    commercial_registration = models.CharField(
        "السجل التجاري",
        max_length=20,
        blank=True,
        default='',
    )
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='core_historicalsponsorship')

    class Meta:
        db_table = 'core_sponsorship'
        verbose_name = "كفالة"
        verbose_name_plural = "الكفالات"
        ordering = ['company_name']

    def __str__(self):
        return self.company_name

    @property
    def name(self):
        """توافق مع _name_only() في forms.py."""
        return self.company_name


class Insurance(BaseModel):
    """التأمين"""
    code = models.CharField("رقم التأمين", max_length=20, unique=True)
    insurance_type = models.CharField("نوع التأمين", max_length=100)
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='core_historicalinsurance')

    class Meta:
        db_table = 'core_insurance'
        verbose_name = "تأمين"
        verbose_name_plural = "التأمينات"
        ordering = ['insurance_type']

    def __str__(self):
        return self.insurance_type

    @property
    def name(self):
        """توافق مع _name_only() في forms.py."""
        return self.insurance_type


class InsuranceClass(BaseModel):
    """فئات التأمين"""
    code = models.CharField("رقم الفئة", max_length=20, unique=True)
    class_type = models.CharField("نوع الفئة", max_length=100)
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='core_historicalinsuranceclass')

    class Meta:
        db_table = 'core_insuranceclass'
        verbose_name = "فئة تأمين"
        verbose_name_plural = "فئات التأمين"
        ordering = ['class_type']

    def __str__(self):
        return self.class_type

    @property
    def name(self):
        """توافق مع _name_only() في forms.py."""
        return self.class_type


class Building(BaseModel):
    """العمارات السكنية للموظفين"""
    code = models.CharField("رقم العمارة", max_length=20, unique=True)
    name = models.CharField("اسم العمارة", max_length=150)
    address = models.CharField("العنوان", max_length=255, blank=True)

    rent_cost = models.DecimalField("الإيجار", max_digits=12, decimal_places=2, default=0)
    water_cost = models.DecimalField("تكلفة الماء", max_digits=12, decimal_places=2, default=0)
    electricity_cost = models.DecimalField("تكلفة الكهرباء", max_digits=12, decimal_places=2, default=0)
    cleaning_cost = models.DecimalField("تكلفة النظافة", max_digits=12, decimal_places=2, default=0)
    transport_cost = models.DecimalField("تكلفة النقل", max_digits=12, decimal_places=2, default=0)
    furniture_cost = models.DecimalField("تكلفة المفروشات", max_digits=12, decimal_places=2, default=0)
    tools_cost = models.DecimalField("تكلفة الأدوات", max_digits=12, decimal_places=2, default=0)

    notes = models.TextField("ملاحظات", blank=True)
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='setup_historicalbuilding')

    class Meta:
        db_table = 'setup_building'
        verbose_name = "عمارة"
        verbose_name_plural = "العمارات"
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_cost(self):
        return (self.rent_cost + self.water_cost + self.electricity_cost +
                self.cleaning_cost + self.transport_cost +
                self.furniture_cost + self.tools_cost)


class Bank(BaseModel):
    """البنوك"""
    code = models.CharField("رقم البنك", max_length=20, unique=True)
    name = models.CharField("اسم البنك", max_length=150)
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='setup_historicalbank')

    class Meta:
        db_table = 'setup_bank'
        verbose_name = "بنك"
        verbose_name_plural = "البنوك"
        ordering = ['name']

    def __str__(self):
        return self.name


class Administration(BaseModel):
    """الإدارات — جدول تهيئة مركزي (رقم + اسم)."""

    class ReportRecipientRole(models.TextChoices):
        NONE = '', '— لا يربط بتقرير مدير'
        OPERATIONS = 'operations_manager', 'مدير العمليات'
        FINANCE = 'finance_manager', 'مدير الحسابات'
        DATA = 'data_manager', 'مدير البيانات'
        PROCUREMENT = 'procurement_manager', 'مدير المشتريات'

    code = models.CharField("رقم الإدارة", max_length=20, unique=True)
    name = models.CharField("اسم الإدارة", max_length=150)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name="مدير الإدارة",
        related_name="managed_administrations",
        null=True,
        blank=True,
    )
    report_recipient_role = models.CharField(
        'تقرير العمليات اليومي',
        max_length=32,
        choices=ReportRecipientRole.choices,
        blank=True,
        default='',
        help_text='يربط موظفي هذه الإدارة بتقرير المدير المحدد في إعدادات التقرير.',
    )
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='setup_historicaladministration')

    class Meta:
        db_table = 'setup_administration'
        verbose_name = "إدارة"
        verbose_name_plural = "الإدارات"
        ordering = ['code', 'name']

    def __str__(self):
        return f'{self.code} — {self.name}' if self.code else self.name
