from django.contrib import admin, messages

from apps.attendance.models import (
    AttendancePunch,
    BiometricDevice,
    BiometricDeviceUser,
    EmployeeBiometricEnrollment,
)


@admin.register(BiometricDevice)
class BiometricDeviceAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'ip_address', 'port', 'branch', 'is_active',
        'has_agent_key', 'connection_status', 'last_sync_at',
    )
    list_filter = ('is_active', 'connection_status', 'branch')
    search_fields = ('name', 'ip_address', 'serial_number')
    readonly_fields = ('agent_api_key',)
    actions = ['regenerate_agent_api_key']

    @admin.display(boolean=True, description='مفتاح وكيل')
    def has_agent_key(self, obj):
        return bool(obj.agent_api_key)

    @admin.action(description='توليد مفتاح وكيل جديد (يُعرض مرة واحدة)')
    def regenerate_agent_api_key(self, request, queryset):
        from apps.attendance.services.agent_keys import set_device_agent_key

        for device in queryset:
            raw = set_device_agent_key(device)
            messages.success(
                request,
                f'جهاز {device.name} (id={device.pk}): {raw}',
            )


@admin.register(BiometricDeviceUser)
class BiometricDeviceUserAdmin(admin.ModelAdmin):
    list_display = ('device_user_id', 'name', 'device', 'card', 'last_synced_at')
    list_filter = ('device',)
    search_fields = ('name', 'card', 'device__name')


@admin.register(EmployeeBiometricEnrollment)
class EmployeeBiometricEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'device', 'device_user_id')
    list_filter = ('device',)
    search_fields = ('employee__name', 'device__name')
    raw_id_fields = ('employee', 'device')


@admin.register(AttendancePunch)
class AttendancePunchAdmin(admin.ModelAdmin):
    list_display = ('punched_at', 'device', 'employee', 'device_user_id', 'device_user_name', 'punch_type')
    list_filter = ('device', 'punch_type')
    date_hierarchy = 'punched_at'
