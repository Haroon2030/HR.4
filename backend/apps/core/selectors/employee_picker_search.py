"""بحث موظفين لاختيار الواجهة — مصدر واحد لكل الصفحات."""
from __future__ import annotations

from apps.core.selectors.employee_search import search_employees
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
    qs = search_employees(qs, q, limit=limit)
    return [employee_picker_dict(emp) for emp in qs]
