"""سياق تبويبات تهيئة الصيانة."""
from __future__ import annotations

from apps.core.decorators import has_permission

MAINTENANCE_SETUP_TAB_KEYS = frozenset({'assets', 'trades', 'workers'})


def resolve_setup_tab(tab: str) -> str:
    tab = (tab or '').strip()
    return tab if tab in MAINTENANCE_SETUP_TAB_KEYS else 'assets'


def maintenance_setup_permissions(user) -> dict:
    return {
        'can_view': has_permission(user, 'maintenance.workers_view'),
        'can_add': has_permission(user, 'maintenance.workers_add'),
        'can_edit': has_permission(user, 'maintenance.workers_edit'),
        'can_delete': has_permission(user, 'maintenance.workers_delete'),
    }


def get_maintenance_setup_tab_context(user, tab: str) -> dict:
    from apps.maintenance.models import MaintenanceAsset, MaintenanceTrade, MaintenanceWorker

    tab = resolve_setup_tab(tab)
    perms = maintenance_setup_permissions(user)
    ctx: dict = {'tab': tab, 'setup_perms': perms}

    if tab == 'assets':
        ctx['assets'] = list(
            MaintenanceAsset.objects.filter(is_deleted=False).order_by('name'),
        )
    elif tab == 'trades':
        ctx['trades'] = list(
            MaintenanceTrade.objects.filter(is_deleted=False).order_by('name'),
        )
    elif tab == 'workers':
        ctx['workers'] = list(
            MaintenanceWorker.objects.filter(is_deleted=False)
            .select_related('trade', 'employee')
            .order_by('name'),
        )
        from django.urls import reverse
        ctx['employee_search_url'] = reverse('web:employee_picker_search')

    return ctx
