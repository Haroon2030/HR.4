"""
Departments Models
نماذج الأقسام
"""
from django.db import models
from apps.core.models import BaseModel
from simple_history.models import HistoricalRecords


class Department(BaseModel):
    """
    Department - القسم
    
    Represents a department within a branch and optionally under a cost center.
    يمثل قسمًا داخل الفرع وبشكل اختياري تحت مركز تكلفة.
    """
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="رقم القسم",
        help_text="رقم تعريف فريد للقسم"
    )
    name = models.CharField(
        max_length=200,
        verbose_name="اسم القسم",
        help_text="الاسم الكامل للقسم"
    )
    branch = models.ForeignKey(
        'core.Branch',
        on_delete=models.SET_NULL,
        related_name='departments',
        null=True,
        blank=True,
        verbose_name="الفرع"
    )
    cost_center = models.ForeignKey(
        'cost_centers.CostCenter',
        on_delete=models.SET_NULL,
        related_name='departments',
        null=True,
        blank=True,
        verbose_name="مركز التكلفة"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="الوصف"
    )
    manager = models.ForeignKey(
        'core.UserProfile',
        on_delete=models.SET_NULL,
        related_name='managed_departments',
        null=True,
        blank=True,
        verbose_name="مدير القسم"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="نشط"
    )
    
    # Audit trail
    history = HistoricalRecords(verbose_name="السجل التاريخي")
    
    class Meta:
        db_table = 'departments'
        verbose_name = "قسم"
        verbose_name_plural = "الأقسام"
        ordering = ['code', 'name']
        indexes = [
            models.Index(fields=['branch', 'code']),
            models.Index(fields=['cost_center']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    @property
    def employees_count(self):
        """عدد الموظفين في هذا القسم"""
        return self.employees.filter(is_deleted=False, user__is_active=True).count()

