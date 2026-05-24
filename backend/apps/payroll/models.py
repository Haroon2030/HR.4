"""
نماذج مسير الرواتب الشهري — Payroll Models
=============================================
هذا الملف يحتوي على نموذجي البيانات الأساسيين لمسير الرواتب:

1. PayrollRun  — المسير الشهري (هيدر)
   يمثل مسير رواتب واحد لفرع واحد في شهر محدد.
   القيد الفريد: (branch, period_year, period_month)
   
2. PayrollLine — سطر المسير (تفاصيل)
   يمثل حساب راتب موظف واحد داخل المسير.
   يحوي snapshot كامل للراتب والخصومات لحظة الحساب.
   القيد الفريد: (run, employee)

مبادئ التصميم:
  - كل بند خصم (غياب، سلفة، مخالفة، إجازة بدون راتب) يُربط بمسير واحد فقط
    عبر الحقل applied_to_payroll على نموذجه الأصلي — يمنع الاحتساب المزدوج.
  - بعد الترحيل (LOCKED) لا يمكن تعديل أي بند.
  - إعادة الفتح (unlock) للسوبر يوزر فقط.
  - HistoricalRecords مُفعّل للتتبع والتدقيق.
"""
from django.db import models
from django.conf import settings
from decimal import Decimal
from simple_history.models import HistoricalRecords

from apps.core.models import BaseModel, Branch


# ══════════════════════════════════════════════════════════════════════════════
# المسير الشهري — PayrollRun (Header)
# ══════════════════════════════════════════════════════════════════════════════

class PayrollRun(BaseModel):
    """
    مسير رواتب شهري لفرع واحد.
    
    دورة الحياة:
      DRAFT (مسودة) → بناء/إعادة بناء → LOCKED (مُرحَّل) → تصدير
      LOCKED → unlock (سوبر يوزر) → DRAFT
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'              # قابل للتعديل وإعادة البناء
        LOCKED = 'locked', 'مُغلق ومُرحَّل'     # مقفل — لا يمكن تعديله
        CANCELLED = 'cancelled', 'مُلغى'       # ملغى (غير مستخدم حالياً)

    class SalaryMode(models.TextChoices):
        CASH = 'cash', 'نقدي'           # موظفون بدون كفالة
        TRANSFER = 'transfer', 'تحويل'  # موظفون على كفالة

    # ── العلاقات ──
    company = models.ForeignKey(
        'core.Company', on_delete=models.PROTECT, related_name='payroll_runs',
        verbose_name="الشركة", null=True, blank=True,
    )
    sponsorship = models.ForeignKey(
        'setup.Sponsorship', on_delete=models.PROTECT, related_name='payroll_runs',
        verbose_name="شركة الكفالة", null=True, blank=True,
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='payroll_runs',
        verbose_name="الفرع"
    )
    salary_mode = models.CharField(
        "نوع الراتب", max_length=20, choices=SalaryMode.choices,
        default=SalaryMode.TRANSFER, db_index=True,
    )

    # ── فترة المسير ──
    period_year = models.PositiveIntegerField("السنة", db_index=True)
    period_month = models.PositiveSmallIntegerField("الشهر", db_index=True)

    # ── الحالة ──
    status = models.CharField(
        "الحالة", max_length=20, choices=Status.choices,
        default=Status.DRAFT, db_index=True
    )

    # ── الإجماليات (مُحسَّبة تلقائياً من أسطر الموظفين عبر recompute_totals) ──
    total_earnings = models.DecimalField("إجمالي الاستحقاقات", max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField("إجمالي الخصومات", max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField("الصافي الكلي", max_digits=14, decimal_places=2, default=0)
    employees_count = models.PositiveIntegerField("عدد الموظفين", default=0)

    # ── بيانات إضافية ──
    notes = models.TextField("ملاحظات", blank=True)
    locked_at = models.DateTimeField("تاريخ الترحيل", null=True, blank=True)         # متى تم الترحيل
    locked_by = models.ForeignKey(                                                     # مَن رحّل المسير
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='locked_payroll_runs', verbose_name="رحَّل بواسطة"
    )
    created_by = models.ForeignKey(                                                    # مَن أنشأ المسير
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_payroll_runs', verbose_name="أنشأ بواسطة"
    )

    # سجل التدقيق التاريخي
    history = HistoricalRecords()

    class Meta:
        verbose_name = "مسير رواتب"
        verbose_name_plural = "مسيرات الرواتب"
        ordering = ['-period_year', '-period_month', 'branch__name']
        unique_together = [
            ('branch', 'period_year', 'period_month', 'salary_mode'),
        ]

    def __str__(self):
        return f"{self.branch.name} — {self.period_year}/{self.period_month:02d}"

    @property
    def period_label(self):
        """اسم الشهر بالعربية + السنة (مثال: يناير 2026)."""
        months_ar = ['', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                     'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
        return f"{months_ar[self.period_month]} {self.period_year}"

    def recompute_totals(self):
        """
        يُعيد حساب إجماليات المسير من مجموع أسطر الموظفين.
        يُستدعى بعد بناء/إعادة بناء المسير.
        """
        agg = self.lines.aggregate(
            e=models.Sum('total_earnings'),
            d=models.Sum('total_deductions'),
            n=models.Sum('net_salary'),
            c=models.Count('id'),
        )
        self.total_earnings = agg['e'] or Decimal('0')
        self.total_deductions = agg['d'] or Decimal('0')
        self.total_net = agg['n'] or Decimal('0')
        self.employees_count = agg['c'] or 0
        self.save(update_fields=[
            'total_earnings', 'total_deductions', 'total_net', 'employees_count'
        ])


# ══════════════════════════════════════════════════════════════════════════════
# سطر المسير — PayrollLine (Detail)
# ══════════════════════════════════════════════════════════════════════════════

class PayrollLine(BaseModel):
    """
    سطر مسير لموظف واحد — snapshot كامل لحظة الحساب.
    
    معادلة الحساب:
      gross = basic + housing + transport + other + cash + meal
      total_earnings = gross + bonus + overtime + other_addition
      total_deductions = absence + unpaid_leave + loan + penalty + insurance + other
      net_salary = total_earnings − total_deductions
    """

    # ── العلاقات ──
    run = models.ForeignKey(
        PayrollRun, on_delete=models.CASCADE, related_name='lines',
        verbose_name="المسير"
    )
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.PROTECT, related_name='payroll_lines',
        verbose_name="الموظف"
    )

    # ══ Snapshot الراتب والبدلات ═════════════════════════════════════
    basic_salary = models.DecimalField("الراتب الأساسي", max_digits=12, decimal_places=2, default=0)
    housing_allowance = models.DecimalField("بدل سكن", max_digits=12, decimal_places=2, default=0)
    transport_allowance = models.DecimalField("بدل نقل", max_digits=12, decimal_places=2, default=0)
    other_allowance = models.DecimalField("بدل إضافي", max_digits=12, decimal_places=2, default=0)
    cash_amount = models.DecimalField("كاش", max_digits=12, decimal_places=2, default=0)
    meal_allowance = models.DecimalField("بدل التغذية", max_digits=12, decimal_places=2, default=0)
    gross_salary = models.DecimalField("إجمالي الراتب", max_digits=12, decimal_places=2, default=0)

    # ══ بيانات الحساب ═══════════════════════════════════════════════
    month_days = models.PositiveIntegerField("أيام الشهر", default=30)           # عدد أيام الشهر (28-31)
    daily_rate = models.DecimalField("سعر اليوم", max_digits=12, decimal_places=2, default=0)  # إجمالي ÷ أيام

    # ══ الخصومات ════════════════════════════════════════════════════
    absence_days = models.DecimalField("أيام الغياب", max_digits=6, decimal_places=1, default=0)
    absence_deduction = models.DecimalField("خصم الغياب", max_digits=12, decimal_places=2, default=0)
    unpaid_leave_days = models.DecimalField("أيام إجازة بدون راتب", max_digits=6, decimal_places=1, default=0)
    unpaid_leave_deduction = models.DecimalField("خصم إجازة بدون راتب", max_digits=12, decimal_places=2, default=0)
    loan_deduction = models.DecimalField("قسط السلفة", max_digits=12, decimal_places=2, default=0)
    penalty_deduction = models.DecimalField("خصم المخالفات", max_digits=12, decimal_places=2, default=0)
    insurance_deduction = models.DecimalField("خصم التأمينات", max_digits=12, decimal_places=2, default=0)
    other_deduction = models.DecimalField("خصومات أخرى", max_digits=12, decimal_places=2, default=0)

    # ══ الإضافات ════════════════════════════════════════════════════
    bonus = models.DecimalField("مكافأة", max_digits=12, decimal_places=2, default=0)
    overtime = models.DecimalField("ساعات إضافية", max_digits=12, decimal_places=2, default=0)
    other_addition = models.DecimalField("إضافات أخرى", max_digits=12, decimal_places=2, default=0)

    # ══ الإجماليات (مُحسَّبة عبر compute_totals) ═══════════════════
    total_earnings = models.DecimalField("إجمالي الاستحقاقات", max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField("إجمالي الخصومات", max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField("الصافي", max_digits=12, decimal_places=2, default=0)

    # ══ التفاصيل ════════════════════════════════════════════════════
    # JSON يحوي أرقام كل بند خصم (IDs) — يُستخدم عند الترحيل لربط البنود
    breakdown = models.JSONField("التفاصيل", default=dict, blank=True)
    notes = models.TextField("ملاحظات", blank=True)

    # سجل التدقيق التاريخي
    history = HistoricalRecords()

    class Meta:
        verbose_name = "سطر مسير"
        verbose_name_plural = "أسطر المسير"
        ordering = ['employee__name']
        unique_together = [('run', 'employee')]  # موظف واحد فقط في كل مسير

    def __str__(self):
        return f"{self.employee.name} — {self.run} = {self.net_salary}"

    def compute_totals(self):
        """
        يحسب الإجماليات من البنود الفرعية.
        يُستدعى قبل save() أثناء بناء المسير.
        """
        # إجمالي الراتب (قبل الخصومات)
        self.gross_salary = (
            Decimal(self.basic_salary or 0)
            + Decimal(self.housing_allowance or 0)
            + Decimal(self.transport_allowance or 0)
            + Decimal(self.other_allowance or 0)
            + Decimal(self.cash_amount or 0)
            + Decimal(self.meal_allowance or 0)
        )
        # إجمالي الاستحقاقات (راتب + إضافات)
        self.total_earnings = (
            self.gross_salary
            + Decimal(self.bonus or 0)
            + Decimal(self.overtime or 0)
            + Decimal(self.other_addition or 0)
        )
        # إجمالي الخصومات
        self.total_deductions = (
            Decimal(self.absence_deduction or 0)
            + Decimal(self.unpaid_leave_deduction or 0)
            + Decimal(self.loan_deduction or 0)
            + Decimal(self.penalty_deduction or 0)
            + Decimal(self.insurance_deduction or 0)
            + Decimal(self.other_deduction or 0)
        )
        # الصافي = الاستحقاقات − الخصومات
        self.net_salary = (self.total_earnings - self.total_deductions).quantize(Decimal('0.01'))
