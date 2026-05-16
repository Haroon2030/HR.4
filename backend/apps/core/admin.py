"""
إدارة الأدوار والمستخدمين وسجلات النسخ الاحتياطي
"""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .backup_download import safe_local_backup_path
from .models import (
    Role,
    UserProfile,
    Company,
    Branch,
    DatabaseBackupLog,
)


class UserProfileInline(admin.StackedInline):
    """عرض ملف المستخدم داخل صفحة المستخدم"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'ملف المستخدم'
    fk_name = 'user'
    extra = 0
    fields = ('role', 'branch', 'assigned_branches', 'phone', 'department', 'position', 'is_protected')
    filter_horizontal = ('assigned_branches',)


class CustomUserAdmin(UserAdmin):
    """
    إدارة المستخدمين مع ملفاتهم
    """
    inlines = [UserProfileInline]
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_active')
    list_filter = ('is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    
    def get_role(self, obj):
        if hasattr(obj, 'profile') and obj.profile.role:
            return obj.profile.role.name
        return '-'
    get_role.short_description = 'الدور'
    get_role.admin_order_field = 'profile__role__name'
    
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """
    إدارة الأدوار
    """
    list_display = ('name', 'role_type', 'is_system_role', 'is_active', 'get_users_count', 'created_at')
    list_filter = ('role_type', 'is_system_role', 'is_active')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('معلومات الدور', {
            'fields': ('name', 'role_type', 'description')
        }),
        ('الإعدادات', {
            'fields': ('is_system_role', 'is_active')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_users_count(self, obj):
        return obj.users.count()
    get_users_count.short_description = 'عدد المستخدمين'
    
    def has_delete_permission(self, request, obj=None):
        """منع حذف أدوار النظام"""
        if obj and obj.is_system_role:
            return False
        return super().has_delete_permission(request, obj)
    
    def get_readonly_fields(self, request, obj=None):
        """جعل نوع الدور للقراءة فقط للأدوار الأساسية"""
        if obj and obj.is_system_role:
            return self.readonly_fields + ('role_type', 'is_system_role')
        return self.readonly_fields


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    إدارة ملفات المستخدمين
    """
    list_display = ('user', 'role', 'branch', 'department', 'position', 'is_protected')
    list_filter = ('role', 'branch', 'is_protected')
    search_fields = ('user__username', 'user__email', 'department', 'position')
    raw_id_fields = ('user',)
    filter_horizontal = ('assigned_branches',)
    
    fieldsets = (
        ('معلومات المستخدم', {
            'fields': ('user', 'role')
        }),
        ('معلومات الفرع', {
            'fields': ('branch', 'assigned_branches'),
            'description': 'الفرع الأساسي للمستخدم، والفروع المكلف بها (للأخصائيين)'
        }),
        ('معلومات العمل', {
            'fields': ('department', 'position', 'phone')
        }),
        ('الإعدادات', {
            'fields': ('is_protected',)
        }),
    )
    
    def has_delete_permission(self, request, obj=None):
        """منع حذف المستخدمين المحميين"""
        if obj and obj.is_protected:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """
    إدارة الشركات
    """
    list_display = ('name', 'tax_number', 'commercial_record', 'contact_phone', 'branches_count')
    search_fields = ('name', 'tax_number', 'commercial_record', 'contact_email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('معلومات الشركة', {
            'fields': ('name', 'tax_number', 'commercial_record', 'logo')
        }),
        ('معلومات التواصل', {
            'fields': ('contact_email', 'contact_phone', 'address')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def branches_count(self, obj):
        return obj.branches.count()
    branches_count.short_description = 'عدد الفروع'


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    """
    إدارة الفروع
    """
    list_display = ('name', 'code', 'company', 'manager', 'is_active', 'employees_count', 'active_employees_count')
    list_filter = ('is_active', 'company')
    search_fields = ('name', 'code', 'address')
    readonly_fields = ('created_at', 'updated_at', 'employees_count', 'active_employees_count')
    raw_id_fields = ('manager',)
    
    fieldsets = (
        ('معلومات الفرع', {
            'fields': ('name', 'code', 'company', 'manager')
        }),
        ('معلومات التواصل', {
            'fields': ('address', 'phone', 'email')
        }),
        ('الإعدادات', {
            'fields': ('is_active',)
        }),
        ('الإحصائيات', {
            'fields': ('employees_count', 'active_employees_count'),
            'classes': ('collapse',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DatabaseBackupLog)
class DatabaseBackupLogAdmin(admin.ModelAdmin):
    """قائمة سجلات النسخ مع تحميل آمن للملف المحلي أو من R2."""

    show_full_result_count = False
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_display = (
        'created_at',
        'trigger',
        'status',
        'filename',
        'display_size_mb',
        'download_link',
    )
    list_filter = ('status', 'trigger')
    search_fields = ('filename', 'r2_key', 'dump_error', 'r2_error')
    readonly_fields = (
        'created_at',
        'trigger',
        'status',
        'filename',
        'display_size_mb',
        'r2_key',
        'dump_error',
        'r2_error',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_module_permission(self, request):
        return request.user.is_staff

    @admin.display(description='الحجم (MB)')
    def display_size_mb(self, obj):
        mb = obj.size_bytes / (1024 * 1024) if obj.size_bytes else 0
        return f'{mb:.2f}'

    @admin.display(description='تحميل')
    def download_link(self, obj: DatabaseBackupLog):
        if obj.status == DatabaseBackupLog.Status.FAILED:
            return '—'
        url = reverse('admin:core_databasebackuplog_download', args=[obj.pk])
        return format_html('<a href="{}">⬇ {}</a>', url, obj.filename)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['subtitle'] = (
            'التحميل من العمود «تحميل». الملف المحلي له أولوية؛ إذا أُزل محلياً يُحمّل من R2 إن وُجد مفتاح.'
        )
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        info = opts.app_label, opts.model_name
        custom = [
            path(
                '<int:object_id>/download-backup/',
                self.admin_site.admin_view(self.download_backup_view),
                name=f'{info[0]}_{info[1]}_download',
            ),
        ]
        return custom + urls

    def download_backup_view(self, request, object_id):
        if not request.user.is_superuser:
            messages.error(request, 'تحميل النسخ الاحتياطية متاح لمدير النظام فقط.')
            return redirect('admin:index')

        obj = get_object_or_404(DatabaseBackupLog, pk=object_id)

        changelist_url = reverse('admin:core_databasebackuplog_changelist')

        if obj.status == DatabaseBackupLog.Status.FAILED:
            messages.error(request, 'نسخ فاشلة — لا يوجد ملف للتحميل.')
            return redirect(changelist_url)

        from apps.core.backup_download import stream_database_backup_file

        try:
            resp = stream_database_backup_file(filename=obj.filename, r2_key=obj.r2_key or '')
        except Exception as exc:
            messages.error(request, f'فشل التحميل من التخزين السحابي: {exc}')
            return redirect(changelist_url)
        if resp is not None:
            return resp

        messages.warning(
            request,
            'الملف غير متوفر محلياً؛ لا توجد نسخة على R2 مرتبطة بهذا السجل.',
        )
        return redirect(changelist_url)


# إعادة تسجيل User مع الـ UserAdmin المخصص
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
