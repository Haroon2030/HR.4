"""
تعديلات الراتب بتاريخ سريان — قاعدة «الشهر كاملاً».

- تاريخ السريان في أي يوم من شهر M ⇒ مسير M كله بالراتب الجديد (لا تقسيم داخل الشهر).
- تعديل لشهر لم يأتِ بعد يبقى معلّقاً ولا يغيّر راتب الموظف الحالي حتى يحين شهره.
- تعديل لشهر سبق ترحيل مسيره ⇒ «فروقات الزيادة» تُصرف في أول مسير مفتوح (مرة واحدة).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

STANDARD_MONTH_DAYS = Decimal('30')


def _month_key(d: date) -> tuple[int, int]:
    return d.year, d.month


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def changes_for(employee) -> list:
    from apps.employees.models import EmployeeSalaryChange

    return list(
        EmployeeSalaryChange.objects.filter(employee_id=employee.pk).order_by('effective_date', 'id')
    )


def basic_salary_for_period(employee, year: int, month: int, changes=None) -> Decimal:
    """الراتب الأساسي الساري لشهر المسير (year, month)."""
    if changes is None:
        changes = changes_for(employee)
    period = (year, month)
    # تعديلات معلّقة حان شهرها (أو سبق) ⇒ أحدثها
    pending = [c for c in changes if not c.applied and _month_key(c.effective_date) <= period]
    if pending:
        return Decimal(pending[-1].new_basic_salary)
    # مسير شهر سابق لتعديل طُبِّق ⇒ الراتب قبل أول تعديل لاحق لذلك الشهر
    later_applied = [c for c in changes if c.applied and _month_key(c.effective_date) > period]
    if later_applied:
        return Decimal(later_applied[0].old_basic_salary)
    return Decimal(employee.basic_salary or 0)


@transaction.atomic
def apply_due_salary_changes(*, as_of: date | None = None, employee=None) -> int:
    """يطبّق على ملف الموظف كل تعديل معلّق حان شهره. يُرجع عدد التعديلات المطبّقة."""
    from apps.employees.models import EmployeeSalaryChange

    as_of = as_of or timezone.localdate()
    qs = EmployeeSalaryChange.objects.select_for_update().filter(applied=False)
    if employee is not None:
        qs = qs.filter(employee_id=employee.pk)
    applied = 0
    for change in qs.select_related('employee').order_by('effective_date', 'id'):
        if _month_key(change.effective_date) > _month_key(as_of):
            continue
        emp = change.employee
        emp.basic_salary = change.new_basic_salary
        emp.save(update_fields=['basic_salary'])
        change.applied = True
        change.applied_at = timezone.now()
        change.save(update_fields=['applied', 'applied_at', 'updated_at'])
        applied += 1
    return applied


@transaction.atomic
def record_salary_change(
    employee, *, new_basic, effective_date: date, user=None, reason: str = '',
    statement=None, as_of: date | None = None,
):
    """يسجّل تعديل راتب بتاريخ سريان، ويطبّقه فوراً إن كان شهره حالياً أو سابقاً."""
    from apps.employees.models import EmployeeSalaryChange

    old_basic = basic_salary_for_period(employee, *_prev_month(*_month_key(effective_date)))
    change = EmployeeSalaryChange.objects.create(
        employee=employee,
        effective_date=effective_date,
        old_basic_salary=old_basic,
        new_basic_salary=Decimal(new_basic),
        reason=reason or '',
        statement=statement,
        created_by=user,
    )
    apply_due_salary_changes(as_of=as_of, employee=employee)
    change.refresh_from_db()
    employee.refresh_from_db(fields=['basic_salary'])
    return change


def salary_arrears_for_period(employee, year: int, month: int, changes=None, *, exclude_run_id=None):
    """
    فروقات زيادة عن أشهر سابقة مُرحَّلة صُرفت بأساسي أقل من الساري لشهرها.

    يُطرح ما سبق صرفه من فروقات في مسيرات مُرحَّلة أخرى، فلا تُصرف مرتين.
    يُرجع قائمة: {year, month, paid_basic, due_basic, days, amount}.
    """
    from apps.payroll.models import PayrollLine, PayrollRun
    from apps.payroll.services.engine import PAYING_RUN_KINDS

    if changes is None:
        changes = changes_for(employee)
    period = (year, month)
    if not any(_month_key(c.effective_date) < period for c in changes):
        return []
    first = min(_month_key(c.effective_date) for c in changes)

    locked = list(
        PayrollLine.objects.filter(
            employee_id=employee.pk,
            run__status=PayrollRun.Status.LOCKED,
            run__run_kind__in=PAYING_RUN_KINDS,
        ).exclude(run_id=exclude_run_id).select_related('run')
    )
    already = {}
    for ln in locked:
        for item in (ln.breakdown or {}).get('salary_arrears') or []:
            key = (int(item['year']), int(item['month']))
            diff = Decimal(item['due_basic']) - Decimal(item['paid_basic'])
            already[key] = already.get(key, Decimal('0')) + diff

    items = []
    for ln in sorted(locked, key=lambda x: (x.run.period_year, x.run.period_month)):
        key = (ln.run.period_year, ln.run.period_month)
        if not (first <= key < period):
            continue
        due = basic_salary_for_period(employee, key[0], key[1], changes)
        paid = Decimal(ln.basic_salary or 0) + already.get(key, Decimal('0'))
        diff = due - paid
        if diff <= 0:
            continue
        period_info = (ln.breakdown or {}).get('period') or {}
        days = Decimal(str(period_info.get('payable_base_days') or '30'))
        amount = (diff * days / STANDARD_MONTH_DAYS).quantize(Decimal('0.01'))
        if amount <= 0:
            continue
        items.append({
            'year': key[0],
            'month': key[1],
            'paid_basic': str(paid),
            'due_basic': str(due),
            'days': str(days),
            'amount': str(amount),
        })
    return items
