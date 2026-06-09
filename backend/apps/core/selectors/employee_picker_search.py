"""بحث موظفين لاختيار الواجهة — مصدر واحد لكل الصفحات."""
from __future__ import annotations

from django.db.models import Q

from apps.core.utils.employee_picker import employee_picker_dict
from apps.core.web_views._helpers import filter_employees_queryset_for_user
from apps.employees.models import Employee


def employee_picker_queryset(user):
    qs = Employee.objects.filter(is_deleted=False).select_related(
        'branch', 'department', 'profession',
    )
    return filter_employees_queryset_for_user(user, qs).order_by('name')


def search_employees_for_picker(user, query: str, *, limit: int = 40) -> list[dict]:
    q = (query or '').strip()
    if not q:
        return []

    qs = employee_picker_queryset(user)
    terms = [t for t in q.split() if t]
    if terms:
        cond = Q()
        for t in terms:
            cond &= (
                Q(name__icontains=t)
                | Q(id_number__icontains=t)
                | Q(employee_number__icontains=t)
                | Q(phone__icontains=t)
                | Q(branch__name__icontains=t)
                | Q(department__name__icontains=t)
                | Q(profession__name__icontains=t)
            )
        qs = qs.filter(cond)

    return [employee_picker_dict(emp) for emp in qs[:limit]]
