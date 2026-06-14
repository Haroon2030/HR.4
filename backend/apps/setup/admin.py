"""Admin لجداول Lookups."""
from django.contrib import admin

from .models import (
    SystemSettings, Nationality, Profession,
    Sponsorship, Insurance, InsuranceClass, Building, Bank, Administration,
    OperationsReportSettings,
)


@admin.register(OperationsReportSettings)
class OperationsReportSettingsAdmin(admin.ModelAdmin):
    list_display = ('recipient_email', 'is_enabled', 'send_hour', 'last_sent_at', 'updated_at')

    def has_add_permission(self, request):
        return not OperationsReportSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'description')
    search_fields = ('key', 'value', 'description')


@admin.register(Nationality)
class NationalityAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(Profession)
class ProfessionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(Sponsorship)
class SponsorshipAdmin(admin.ModelAdmin):
    list_display = ('code', 'company_name', 'commercial_registration', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'company_name', 'commercial_registration')


@admin.register(Insurance)
class InsuranceAdmin(admin.ModelAdmin):
    list_display = ('code', 'insurance_type', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'insurance_type')


@admin.register(InsuranceClass)
class InsuranceClassAdmin(admin.ModelAdmin):
    list_display = ('code', 'class_type', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'class_type')


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'rent_cost', 'water_cost', 'electricity_cost', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'address')


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(Administration)
class AdministrationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'manager', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    autocomplete_fields = ('manager',)
