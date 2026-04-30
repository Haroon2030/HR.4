"""
Departments Admin
لوحة إدارة الأقسام
"""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Department


@admin.register(Department)
class DepartmentAdmin(SimpleHistoryAdmin):
    """إدارة الأقسام"""
    list_display = ['code', 'name', 'branch', 'cost_center', 'manager', 'is_active', 'employees_count', 'created_at']
    list_filter = ['is_active', 'branch', 'cost_center', 'created_at']
    search_fields = ['code', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['branch', 'cost_center', 'manager']
    
    fieldsets = (
        ('المعلومات الأساسية', {
            'fields': ('code', 'name', 'branch', 'cost_center', 'description')
        }),
        ('الإدارة', {
            'fields': ('manager',)
        }),
        ('الحالة', {
            'fields': ('is_active',)
        }),
        ('معلومات التدقيق', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def employees_count(self, obj):
        """عدد الموظفين"""
        return obj.employees_count
    employees_count.short_description = 'عدد الموظفين'
