"""حساب رصيد الإجازات — موحّد بين تبويب الإجازات والتصفية والمخصصات."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.employees.services.settlement_eosb import compute_tiered_leave_accrued_days

LEAVE_DAYS_QUANT = Decimal('0.01')


def employee_service_days(employee, *, as_of: date | None = None) -> int:
    """أيام الخدمة من تاريخ المباشرة حتى تاريخ التصفية أو اليوم."""
    hire = getattr(employee, 'hire_date', None)
    if not hire:
        return 0
    end = getattr(employee, 'end_date', None) or as_of or timezone.localdate()
    days = (end - hire).days
    return max(days, 0)


def compute_employee_accrued_leave_days(employee, *, as_of: date | None = None) -> Decimal:
    """
    الرصيد المستحق: 21 يوم/سنة أول 5 سنوات، 30 يوم/سنة من السنة السادسة.
    يُحسب فقط عند وجود تاريخ مباشرة وكفالة.
    """
    if not employee.hire_date or not employee.sponsorship_id:
        return Decimal('0.00')
    service_days = employee_service_days(employee, as_of=as_of)
    if service_days <= 0:
        return Decimal('0.00')
    return compute_tiered_leave_accrued_days(service_days)


def sum_annual_leave_days_taken(employee) -> Decimal:
    """مجموع أيام الإجازات السنوية المُسجَّلة في النظام."""
    from apps.employees.models import EmployeeLeave

    total = (
        EmployeeLeave.objects.filter(
            employee_id=employee.pk,
            leave_type=EmployeeLeave.LeaveType.ANNUAL,
        ).aggregate(total=Sum('days'))['total']
    )
    return Decimal(total or 0).quantize(LEAVE_DAYS_QUANT)


def resolve_used_leave_days(employee) -> Decimal:
    """
    أيام الإجازة المستخدمة:
    - إن وُجدت سجلات إجازة سنوية → المجموع من السجلات (مصدر الحقيقة)
    - وإلا → الحقل اليدوي available_leave_balance (تراث/إدخال يدوي)
    """
    from apps.employees.models import EmployeeLeave

    stored = Decimal(employee.available_leave_balance or 0).quantize(LEAVE_DAYS_QUANT)
    has_annual = EmployeeLeave.objects.filter(
        employee_id=employee.pk,
        leave_type=EmployeeLeave.LeaveType.ANNUAL,
    ).exists()
    if has_annual:
        return sum_annual_leave_days_taken(employee)
    return stored


def compute_employee_remaining_leave_days(employee, *, as_of: date | None = None) -> Decimal:
    """المتبقي = المستحق − المستخدم (لا يقل عن صفر)."""
    accrued = compute_employee_accrued_leave_days(employee, as_of=as_of)
    used = resolve_used_leave_days(employee)
    remaining = (accrued - used).quantize(LEAVE_DAYS_QUANT)
    if remaining < 0:
        return Decimal('0.00')
    return remaining
