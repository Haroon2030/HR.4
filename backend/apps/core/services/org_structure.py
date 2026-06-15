"""تحميل بيانات تبويب واحد من شاشة الهيكل التنظيمي."""
from __future__ import annotations

from django.db.models import Count, Q

from apps.core.models import Branch
from apps.core.permission_policy import org_structure_permissions
from apps.core.services.access_control import filter_branches_queryset, get_accessible_branch_ids
from apps.core.services.setup_cache import get_cached_list
ORG_STRUCTURE_TAB_KEYS = frozenset({
    'branches', 'cost_centers', 'departments', 'administrations',
    'nationalities', 'professions', 'sponsorships', 'insurances',
    'insurance_classes', 'buildings', 'banks',
})

_BRANCH_EMPLOYEES = Count(
    'employee_records',
    filter=Q(employee_records__is_deleted=False),
    distinct=True,
)
_CC_DEPARTMENTS = Count(
    'departments',
    filter=Q(departments__is_deleted=False),
    distinct=True,
)
_DEPT_EMPLOYEES = Count(
    'employee_records',
    filter=Q(employee_records__is_deleted=False),
    distinct=True,
)


def resolve_org_tab(tab: str) -> str:
    tab = (tab or '').strip()
    return tab if tab in ORG_STRUCTURE_TAB_KEYS else 'branches'


def get_org_tab_context(user, tab: str) -> dict:
    """سياق قالب لتبويب واحد فقط — يقلّل استعلامات الصفحة الأولى."""
    from apps.cost_centers.models import CostCenter
    from apps.departments.models import Department
    from apps.setup.models import (
        Administration, Bank, Building, Insurance, InsuranceClass,
        Nationality, Profession, Sponsorship,
    )

    tab = resolve_org_tab(tab)
    ctx: dict = {
        'tab': tab,
        'org_perms': org_structure_permissions(user),
    }
    branch_ids = get_accessible_branch_ids(user)

    if tab == 'branches':
        ctx['branches'] = list(filter_branches_queryset(
            user,
            Branch.objects.select_related('company', 'manager')
            .annotate(emp_count=_BRANCH_EMPLOYEES),
        ))
    elif tab == 'cost_centers':
        qs = CostCenter.objects.select_related('branch').annotate(
            dept_count=_CC_DEPARTMENTS,
        ).order_by('branch__name', 'name')
        if branch_ids is not None:
            qs = qs.filter(branch_id__in=branch_ids)
        ctx['cost_centers'] = list(qs)
    elif tab == 'departments':
        qs = Department.objects.select_related(
            'branch', 'cost_center', 'manager',
        ).annotate(emp_count=_DEPT_EMPLOYEES).order_by('branch__name', 'name')
        if branch_ids is not None:
            qs = qs.filter(branch_id__in=branch_ids)
        ctx['departments'] = list(qs)
    elif tab == 'administrations':
        ctx['administrations'] = get_cached_list(
            'administrations',
            lambda: list(
                Administration.objects.filter(is_deleted=False)
                .select_related('manager')
                .order_by('code', 'name'),
            ),
        )
    elif tab == 'nationalities':
        ctx['nationalities'] = get_cached_list(
            'nationalities', lambda: Nationality.objects.all(),
        )
    elif tab == 'professions':
        ctx['professions'] = get_cached_list(
            'professions', lambda: Profession.objects.all(),
        )
    elif tab == 'sponsorships':
        ctx['sponsorships'] = get_cached_list(
            'sponsorships', lambda: Sponsorship.objects.all(),
        )
    elif tab == 'insurances':
        ctx['insurances'] = get_cached_list(
            'insurances', lambda: Insurance.objects.all(),
        )
    elif tab == 'insurance_classes':
        ctx['insurance_classes'] = get_cached_list(
            'insurance_classes', lambda: InsuranceClass.objects.all(),
        )
    elif tab == 'buildings':
        ctx['buildings'] = get_cached_list(
            'buildings',
            lambda: Building.objects.filter(is_deleted=False).order_by('name'),
        )
    elif tab == 'banks':
        ctx['banks'] = get_cached_list(
            'banks',
            lambda: Bank.objects.filter(is_deleted=False).order_by('name'),
        )

    return ctx
