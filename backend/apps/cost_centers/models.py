"""
Cost Centers Models
نماذج مراكز التكلفة
"""
from django.db import models
from apps.core.models import BaseModel
from simple_history.models import HistoricalRecords


class CostCenter(BaseModel):
    """
    Cost Center - مركز التكلفة
    
    Represents a cost center within a branch for budget tracking and reporting.
    يمثل مركز تكلفة داخل الفرع لتتبع الميزانية وإعداد التقارير.
    """
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="رقم المركز",
        help_text="رقم تعريف فريد لمركز التكلفة"
    )
    name = models.CharField(
        max_length=200,
        verbose_name="اسم المركز",
        help_text="الاسم الكامل لمركز التكلفة"
    )
    branch = models.ForeignKey(
        'core.Branch',
        on_delete=models.SET_NULL,
        related_name='cost_centers',
        null=True,
        blank=True,
        verbose_name="الفرع"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="الوصف"
    )
    budget = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="الميزانية",
        help_text="الميزانية السنوية المخصصة"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="نشط"
    )
    
    # Audit trail
    history = HistoricalRecords(verbose_name="السجل التاريخي")
    
    class Meta:
        db_table = 'cost_centers'
        verbose_name = "مركز تكلفة"
        verbose_name_plural = "مراكز التكلفة"
        ordering = ['code', 'name']
        indexes = [
            models.Index(fields=['branch', 'code']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    @property
    def departments_count(self):
        """عدد الأقسام في هذا المركز"""
        return self.departments.filter(is_deleted=False).count()

