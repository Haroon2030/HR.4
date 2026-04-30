"""
Cost Centers Admin
لوحة إدارة مراكز التكلفة
"""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import CostCenter


@admin.register(CostCenter)
class CostCenterAdmin(SimpleHistoryAdmin):
    """إدارة مراكز التكلفة"""
    list_display = ['code', 'name', 'branch', 'budget', 'is_active', 'departments_count', 'created_at']
    list_filter = ['is_active', 'branch', 'created_at']
    search_fields = ['code', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['branch']
    
    fieldsets = (
        ('المعلومات الأساسية', {
            'fields': ('code', 'name', 'branch', 'description')
        }),
        ('الميزانية', {
            'fields': ('budget',)
        }),
        ('الحالة', {
            'fields': ('is_active',)
        }),
        ('معلومات التدقيق', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def departments_count(self, obj):
        """عدد الأقسام"""
        return obj.departments_count
    departments_count.short_description = 'عدد الأقسام'
