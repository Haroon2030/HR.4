"""إنشاء قيد افتتاحي للمخصصات بعد استيراد أرصدة الترحيل."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.core.salary_month import daily_rate_from_total
from apps.employees.models import Employee, EmployeeLedger
from apps.employees.services.migration_balance import (
    compute_opening_eosb_amount,
    compute_opening_leave_days,
    employee_leave_accrual_start,
    global_cutover_date,
)


def build_migration_initial_ledger_notes(
    *,
    employee: Employee,
    cutover_date: date,
    leave_days: Decimal,
    leave_amount: Decimal,
    eosb_amount: Decimal,
) -> str:
    hire = employee.hire_date or '—'
    start = employee_leave_accrual_start(employee) or cutover_date
    return (
        f'عملية: رصيد افتتاحي (ترحيل من نظام سابق)\n'
        f'تاريخ الانتقال: {cutover_date} | بدء احتساب الإجازة: {start}\n'
        f'تاريخ المباشرة الحقيقي (لـ EOSB): {hire}\n'
        f'── الإجازات ──\n'
        f'رصيد إجازة افتتاحي مستورد: {leave_days} يوم = {leave_amount} ر.س\n'
        f'── مكافأة نهاية الخدمة (مخصص محاسبي) ──\n'
        f'مخصص EOSB افتتاحي مستورد: {eosb_amount} ر.س\n'
        f'ملاحظة: التصفية النهائية لـ EOSB تُحسب من تاريخ المباشرة الحقيقي.'
    )


@transaction.atomic
def apply_opening_balance_to_employee(
    employee: Employee,
    *,
    opening_leave_days: Decimal,
    opening_eosb_amount: Decimal,
    cutover_date: date | None = None,
    leave_accrual_start_date: date | None = None,
    created_by=None,
    replace_existing: bool = False,
) -> EmployeeLedger:
    """
    يحفظ الأرصدة الافتتاحية على الموظف وينشئ قيد INITIAL_BALANCE.
    يُرفع migration_locked=True بعد النجاح.
    """
    if employee.migration_locked and not replace_existing:
        raise ValueError(f'الموظف {employee.name} معتمد مسبقاً — لا يمكن إعادة الاستيراد.')

    cutover = cutover_date or leave_accrual_start_date or global_cutover_date()
    if not cutover:
        raise ValueError('يجب تحديد تاريخ الانتقال (HR_MIGRATION_CUTOVER_DATE أو في الملف).')

    accrual_start = leave_accrual_start_date or cutover
    leave_days = Decimal(opening_leave_days or 0).quantize(Decimal('0.01'))
    eosb_amount = Decimal(opening_eosb_amount or 0).quantize(Decimal('0.01'))
    daily = daily_rate_from_total(employee.total_salary)
    leave_amount = (leave_days * daily).quantize(Decimal('0.01'))

    if replace_existing:
        EmployeeLedger.all_objects.filter(
            employee=employee,
            transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
        ).delete()

    if EmployeeLedger.objects.filter(
        employee=employee,
        transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
    ).exists() and not replace_existing:
        raise ValueError(f'الموظف {employee.name} لديه رصيد افتتاحي مسبق في المخصصات.')

    employee.opening_leave_days = leave_days
    employee.opening_eosb_amount = eosb_amount
    employee.leave_accrual_start_date = accrual_start
    employee.available_leave_balance = Decimal('0')
    employee.migration_locked = True
    employee.save(update_fields=[
        'opening_leave_days',
        'opening_eosb_amount',
        'leave_accrual_start_date',
        'available_leave_balance',
        'migration_locked',
        'updated_at',
    ])

    notes = build_migration_initial_ledger_notes(
        employee=employee,
        cutover_date=cutover,
        leave_days=leave_days,
        leave_amount=leave_amount,
        eosb_amount=eosb_amount,
    )

    return EmployeeLedger.objects.create(
        employee=employee,
        transaction_type=EmployeeLedger.TransactionType.INITIAL_BALANCE,
        date=cutover,
        leave_days_change=leave_days,
        leave_amount_change=leave_amount,
        eosb_amount_change=eosb_amount,
        cumulative_leave_days=leave_days,
        cumulative_leave_amount=leave_amount,
        cumulative_eosb_amount=eosb_amount,
        notes=notes,
        created_by=created_by,
    )
