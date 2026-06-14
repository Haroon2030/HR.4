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

    recipient_email = models.EmailField('البريد المستلم', blank=True, default='')
    is_enabled = models.BooleanField('تفعيل الإرسال التلقائي', default=False)
    send_time = models.TimeField(
        'وقت الإرسال',
        default=time(12, 0, 0),
        help_text='يُرسل التقرير يومياً عند هذا الوقت (توقيت السيرفر).',
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
    is_active = models.BooleanField("نشط", default=True)

    history = HistoricalRecords(table_name='setup_historicaladministration')

    class Meta:
        db_table = 'setup_administration'
        verbose_name = "إدارة"
        verbose_name_plural = "الإدارات"
        ordering = ['code', 'name']

    def __str__(self):
        return f'{self.code} — {self.name}' if self.code else self.name
