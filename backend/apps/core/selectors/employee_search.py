"""بحث موظفين موحّد — حقول مباشرة + استعلامات فرعية بدلاً من JOINs متعددة."""
from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.core.models import Branch
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department
from apps.employees.models import Employee
from apps.setup.models import Nationality, Profession


def _ids_for_term(model, field: str, term: str, *, limit: int = 80) -> list[int]:
    return list(
        model.objects.filter(**{f'{field}__icontains': term})
        .values_list('pk', flat=True)[:limit]
    )


def employee_search_q_for_term(term: str) -> Q:
    """شروط بحث لمصطلح واحد — يفضّل الحقول المفهرسة على الموظف."""
    t = (term or '').strip()
    if not t:
        return Q()

    q = (
        Q(name__icontains=t)
        | Q(id_number__icontains=t)
        | Q(employee_number__icontains=t)
        | Q(phone__icontains=t)
        | Q(status__icontains=t)
        | Q(email__icontains=t)
    )

    branch_ids = _ids_for_term(Branch, 'name', t)
    if branch_ids:
        q |= Q(branch_id__in=branch_ids)

    dept_ids = _ids_for_term(Department, 'name', t)
    if dept_ids:
        q |= Q(department_id__in=dept_ids)

    cc_ids = _ids_for_term(CostCenter, 'name', t)
    if cc_ids:
        q |= Q(cost_center_id__in=cc_ids)

    nat_ids = _ids_for_term(Nationality, 'name', t)
    if nat_ids:
        q |= Q(nationality_id__in=nat_ids)

    prof_ids = _ids_for_term(Profession, 'name', t)
    if prof_ids:
        q |= Q(profession_id__in=prof_ids)

    return q


def apply_employee_search(qs: QuerySet, query: str) -> QuerySet:
    """تطبيق بحث متعدد الكلمات على queryset موظفين."""
    terms = [t for t in (query or '').split() if t]
    if not terms:
        return qs
    for term in terms:
        qs = qs.filter(employee_search_q_for_term(term))
    return qs


def search_employees(
    qs: QuerySet,
    query: str,
    *,
    limit: int | None = None,
) -> QuerySet:
    """بحث مع ترتيب افتراضي."""
    qs = apply_employee_search(qs, query)
    qs = qs.order_by('name', 'id')
    if limit is not None:
        return qs[:limit]
    return qs
