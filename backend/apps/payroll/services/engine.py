"""
محرك حساب مسير الرواتب الشهري — Payroll Engine
=================================================
هذا الملف هو قلب نظام الرواتب. يحتوي على 3 دوال رئيسية:

1. build_payroll_run(branch, year, month, user)
   ────────────────────────────────────────────
   يبني/يعيد بناء مسير DRAFT لفرع وشهر محددين.
   لكل موظف نشط أو في إجازة:
     - يحسب الراتب الإجمالي = أساسي + سكن + نقل + إضافي + كاش
     - يحسب خصم الغياب من سجلات EmployeeAbsence (أجر اليوم = الإجمالي ÷ 30)
     - يحسب خصم الإجازات بدون راتب من EmployeeLeave
     - يحسب قسط السلفة من LoanInstallment
     - يحسب المخالفات من EmployeeStatement (نوع PENALTY)
     - يحسب خصم التأمينات = إجمالي × نسبة التأمين / 100
     - يُحفظ كل شيء في PayrollLine

2. lock_payroll_run(run, user)
   ──────────────────────────
   يُرحّل المسير ويربط كل بنود الخصم به:
     - الغيابات والإجازات → applied_to_payroll = run
     - أقساط السلف → applied_to_payroll + status = PAID
     - المخالفات → applied_to_payroll = run
   بعد الترحيل لا يمكن تعديل المسير.

3. unlock_payroll_run(run, user)
   ─────────────────────────────
   يفك ربط كل البنود ويعيد المسير لحالة DRAFT.
   ⚠️ للسوبر يوزر فقط — الفحص يتم في الـ View.

مبدأ مهم:
  - البناء يعمل بنظام Snapshot: يلتقط صورة من البيانات الحالية.
  - البنود لا تُربط حتى يتم الترحيل (lock).
  - إذا تغيّرت البيانات بعد البناء، يجب عمل Rebuild.
"""
from collections import defaultdict
from decimal import Decimal
from datetime import date
from django.db import transaction

from apps.core.salary_month import (
    calendar_period_bounds,
    calendar_month_last_day,
    daily_rate_from_total,
    deduction_for_days,
    salary_month_days,
)
from django.db.models import Q
from django.utils import timezone

from apps.payroll.models import PayrollRun, PayrollLine
from apps.employees.models import (
    Employee, EmployeeAbsence, EmployeeLeave, EmployeeStatement, LoanInstallment
)


def _q(v):
    """تقريب القيمة لرقمين عشريين (لمنع أخطاء الكسور)."""
    return Decimal(v or 0).quantize(Decimal('0.01'))


def _applied_filter(run):
    return Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll_id=run.pk)


def _group_by_employee_id(rows, attr='employee_id'):
    grouped = defaultdict(list)
    for row in rows:
        grouped[getattr(row, attr)].append(row)
    return grouped


def _bulk_payroll_deductions(employee_ids, run, period_start, period_end, year, month):
    """جلب كل بنود الخصم للموظفين دفعة واحدة."""
    if not employee_ids:
        return {}, {}, {}, {}, set()

    applied = _applied_filter(run)

    absences = EmployeeAbsence.objects.filter(
        employee_id__in=employee_ids,
        absence_date__range=(period_start, period_end),
    ).filter(applied)

    unpaid_leaves = EmployeeLeave.objects.filter(
        employee_id__in=employee_ids,
        leave_type=EmployeeLeave.LeaveType.UNPAID,
        date_from__lte=period_end,
        date_to__gte=period_start,
    ).filter(applied)

    installments = LoanInstallment.objects.filter(
        loan__employee_id__in=employee_ids,
        period_year=year,
        period_month=month,
        status=LoanInstallment.Status.PENDING,
    ).filter(applied)

    penalties = EmployeeStatement.objects.filter(
        employee_id__in=employee_ids,
        statement_type=EmployeeStatement.StatementType.PENALTY,
        statement_date__range=(period_start, period_end),
    ).filter(applied)

    locked_emp_ids = set(
        PayrollLine.objects.filter(
            employee_id__in=employee_ids,
            run__period_year=year,
            run__period_month=month,
            run__status=PayrollRun.Status.LOCKED,
            run__run_kind=PayrollRun.RunKind.STANDARD,
        )
        .exclude(run_id=run.pk)
        .values_list('employee_id', flat=True)
    )

    inst_by_emp = defaultdict(list)
    for inst in installments.select_related('loan'):
        inst_by_emp[inst.loan.employee_id].append(inst)

    return (
        _group_by_employee_id(absences),
        _group_by_employee_id(unpaid_leaves),
        inst_by_emp,
        _group_by_employee_id(penalties),
        locked_emp_ids,
    )


def _unpaid_leave_days_in_period(leave, period_start, period_end):
    s = max(leave.date_from, period_start)
    e = min(leave.date_to, period_end)
    if e < s:
        return Decimal('0')
    return Decimal((e - s).days + 1)


# ══════════════════════════════════════════════════════════════════════════════
# 1. بناء المسير
# ══════════════════════════════════════════════════════════════════════════════

def _employees_for_payroll_run(branch, salary_mode, *, sponsorship_id=None, year=None, month=None):
    """موظفون مسير الفرع — مع قاعدة النقل (راتب كامل للفرع الجديد)."""
    if year is not None and month is not None:
        from apps.payroll.services.transfer_payroll import employees_queryset_for_branch_payroll
        return employees_queryset_for_branch_payroll(
            branch, salary_mode, sponsorship_id=sponsorship_id, year=year, month=month,
        )
    from apps.employees.models import Employee

    qs = Employee.objects.filter(
        branch=branch,
        status__in=[Employee.Status.ACTIVE, Employee.Status.LEAVE],
    )
    if salary_mode == PayrollRun.SalaryMode.CASH:
        return qs.filter(sponsorship__isnull=True)
    if salary_mode == PayrollRun.SalaryMode.TRANSFER:
        qs = qs.filter(sponsorship__isnull=False)
        if sponsorship_id:
            qs = qs.filter(sponsorship_id=sponsorship_id)
        return qs
    raise ValueError('نوع الراتب غير صالح.')


def _compute_employee_payroll_snapshot(
    emp,
    year: int,
    month: int,
    *,
    run: PayrollRun | None,
    abs_by_emp=None,
    leaves_by_emp=None,
    inst_by_emp=None,
    pen_by_emp=None,
) -> dict:
    """حساب snapshot راتب موظف لشهر — يُستخدم في المسير العادي والتفصيلي."""
    period_start, period_end = calendar_period_bounds(year, month)
    month_days = salary_month_days(year, month)

    if abs_by_emp is None:
        if run is None:
            raise ValueError('run مطلوب لحساب الخصومات.')
        abs_by_emp, leaves_by_emp, inst_by_emp, pen_by_emp, _ = _bulk_payroll_deductions(
            [emp.id], run, period_start, period_end, year, month,
        )

    emp_absences = abs_by_emp.get(emp.id, [])
    emp_leaves = leaves_by_emp.get(emp.id, [])
    emp_installments = inst_by_emp.get(emp.id, [])
    emp_penalties = pen_by_emp.get(emp.id, [])

    gross = (
        Decimal(emp.basic_salary or 0)
        + Decimal(emp.housing_allowance or 0)
        + Decimal(emp.transport_allowance or 0)
        + Decimal(emp.other_allowance or 0)
        + Decimal(emp.cash_amount or 0)
        + Decimal(emp.meal_allowance or 0)
    )
    daily_rate = daily_rate_from_total(gross)

    absence_deduction = _q(
        sum(
            (deduction_for_days(gross, a.days) for a in emp_absences),
            Decimal('0'),
        )
    )
    unpaid_days = sum(
        (_unpaid_leave_days_in_period(lv, period_start, period_end) for lv in emp_leaves),
        Decimal('0'),
    )
    unpaid_leave_deduction = _q(daily_rate * unpaid_days)
    loan_deduction = _q(sum((Decimal(i.amount) for i in emp_installments), Decimal('0')))
    penalty_deduction = _q(
        sum((Decimal(p.deduction_amount or 0) for p in emp_penalties), Decimal('0'))
    )
    rate = Decimal(emp.insurance_deduction_rate or 0)
    insurance_deduction = _q(gross * rate / Decimal('100'))
    total_deductions = _q(
        absence_deduction + unpaid_leave_deduction + loan_deduction
        + penalty_deduction + insurance_deduction
    )
    net_salary = _q(gross - total_deductions)

    return {
        'gross_salary': gross,
        'daily_rate': daily_rate,
        'month_days': month_days,
        'absence_days': sum((a.days for a in emp_absences), 0),
        'absence_deduction': absence_deduction,
        'unpaid_leave_days': unpaid_days,
        'unpaid_leave_deduction': unpaid_leave_deduction,
        'loan_deduction': loan_deduction,
        'penalty_deduction': penalty_deduction,
        'insurance_deduction': insurance_deduction,
        'total_earnings': gross,
        'total_deductions': total_deductions,
        'net_salary': net_salary,
        'breakdown': {
            'absences': [
                {
                    'id': a.id,
                    'date': a.absence_date.isoformat(),
                    'days': a.days,
                    'amount': str(deduction_for_days(gross, a.days)),
                }
                for a in emp_absences
            ],
            'unpaid_leaves': [
                {'id': l.id, 'from': l.date_from.isoformat(), 'to': l.date_to.isoformat()}
                for l in emp_leaves
            ],
            'loan_installments': [
                {'id': i.id, 'loan_id': i.loan_id, 'amount': str(i.amount)}
                for i in emp_installments
            ],
            'penalties': [
                {'id': p.id, 'title': p.title, 'amount': str(p.deduction_amount)}
                for p in emp_penalties
            ],
            'insurance_rate': str(rate),
        },
    }


@transaction.atomic
def build_payroll_run(branch, year: int, month: int, user=None, *, salary_mode=None, sponsorship_id=None):
    """
    يبني أو يُعيد بناء مسير DRAFT لفرع وشهر محددين.

    يستخدم select_for_update لقفل صف المسير ومنع البناء المتوازي.
    يحذف الأسطر القديمة ويعيد حسابها من الصفر (Snapshot).

    المخرجات: PayrollRun محدّث مع totals محسوبة.
    الأخطاء: ValueError إذا كان المسير مغلقاً (LOCKED).
    """
    if salary_mode is None:
        salary_mode = PayrollRun.SalaryMode.TRANSFER
    if salary_mode not in PayrollRun.SalaryMode.values:
        raise ValueError('نوع الراتب غير صالح.')

    if salary_mode == PayrollRun.SalaryMode.CASH:
        sponsorship_id = None
    elif salary_mode == PayrollRun.SalaryMode.TRANSFER and not sponsorship_id:
        raise ValueError('يرجى اختيار شركة الكفالة لمسير التحويل.')

    # ── جلب أو إنشاء المسير ──
    run, _ = PayrollRun.objects.get_or_create(
        branch=branch,
        period_year=year,
        period_month=month,
        salary_mode=salary_mode,
        run_kind=PayrollRun.RunKind.STANDARD,
        defaults={
            'created_by': user,
            'status': PayrollRun.Status.DRAFT,
            'company': branch.company,
            'sponsorship_id': sponsorship_id,
        },
    )
    update_fields = []
    if run.company_id != branch.company_id:
        run.company = branch.company
        update_fields.append('company')
    if run.sponsorship_id != sponsorship_id:
        run.sponsorship_id = sponsorship_id
        update_fields.append('sponsorship_id')
    if update_fields:
        run.save(update_fields=update_fields)

    # لا يمكن إعادة بناء مسير مُرحَّل
    if run.status == PayrollRun.Status.LOCKED:
        raise ValueError('المسير مُغلق ولا يمكن إعادة بنائه. أعد فتحه أولاً.')

    # قفل صف المسير لمنع أي عملية بناء متوازية (race condition)
    PayrollRun.objects.select_for_update().filter(pk=run.pk).first()

    # حذف الأسطر القديمة حذفاً فعلياً (hard delete) لتجنب تعارض القيد الفريد
    PayrollLine.all_objects.filter(run=run).delete()

    # ── حدود الشهر: فترة تقويمية للتصفية، 30 يوماً لقسمة الراتب ──
    period_start, period_end = calendar_period_bounds(year, month)
    month_days = salary_month_days(year, month)

    from apps.payroll.services.transfer_payroll import (
        transfer_breakdown_for_employee,
        transfers_in_period,
    )
    company_transfers = transfers_in_period(branch.company_id, year, month)

    # ── جلب الموظفين حسب نوع الراتب + قاعدة النقل ──
    employees = list(
        _employees_for_payroll_run(
            branch, salary_mode, sponsorship_id=sponsorship_id, year=year, month=month,
        ).order_by('name').distinct()
    )
    employee_ids = [e.id for e in employees]
    abs_by_emp, leaves_by_emp, inst_by_emp, pen_by_emp, locked_emp_ids = _bulk_payroll_deductions(
        employee_ids, run, period_start, period_end, year, month,
    )

    lines_to_create = []
    seen_ids = set()

    for emp in employees:
        if emp.id in seen_ids:
            continue
        seen_ids.add(emp.id)

        if emp.id in locked_emp_ids:
            continue

        snap = _compute_employee_payroll_snapshot(
            emp, year, month, run=run,
            abs_by_emp=abs_by_emp,
            leaves_by_emp=leaves_by_emp,
            inst_by_emp=inst_by_emp,
            pen_by_emp=pen_by_emp,
        )
        breakdown = dict(snap['breakdown'])
        transfer_info = transfer_breakdown_for_employee(company_transfers.get(emp.id))
        if transfer_info:
            breakdown['transfer'] = transfer_info

        line = PayrollLine(
            run=run,
            employee=emp,
            basic_salary=emp.basic_salary or 0,
            housing_allowance=emp.housing_allowance or 0,
            transport_allowance=emp.transport_allowance or 0,
            other_allowance=emp.other_allowance or 0,
            cash_amount=emp.cash_amount or 0,
            meal_allowance=emp.meal_allowance or 0,
            month_days=snap['month_days'],
            daily_rate=snap['daily_rate'],
            absence_days=snap['absence_days'],
            absence_deduction=snap['absence_deduction'],
            unpaid_leave_days=snap['unpaid_leave_days'],
            unpaid_leave_deduction=snap['unpaid_leave_deduction'],
            loan_deduction=snap['loan_deduction'],
            penalty_deduction=snap['penalty_deduction'],
            insurance_deduction=snap['insurance_deduction'],
            gross_salary=snap['gross_salary'],
            total_earnings=snap['total_earnings'],
            total_deductions=snap['total_deductions'],
            net_salary=snap['net_salary'],
            breakdown=breakdown,
        )
        lines_to_create.append(line)

    if lines_to_create:
        PayrollLine.objects.bulk_create(lines_to_create, batch_size=500)

    # تحديث إجمالي المسير (مجموع كل الأسطر)
    run.recompute_totals()
    return run


# ══════════════════════════════════════════════════════════════════════════════
# 2. ترحيل المسير (قفل) — ربط البنود ومنع التعديل
# ══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def lock_payroll_run(run: PayrollRun, user):
    """
    يُرحّل المسير ويربط كل بنود الخصم به.

    عملية الربط (applied_to_payroll):
      - تمنع احتساب نفس البند في مسير آخر
      - تُعلّم أقساط السلفة كمدفوعة (PAID)
      - إذا اكتملت كل أقساط السلفة، تُحدَّث حالتها لـ PAID

    الأخطاء: ValueError إذا كان المسير مُغلقاً بالفعل.
    """
    if run.status == PayrollRun.Status.LOCKED:
        raise ValueError('المسير مُغلق بالفعل.')

    from apps.employees.models import EmployeeLedger, EmployeeLoan
    from apps.employees.services.accrual_ledger_notes import (
        MONTHLY_LEAVE_ACCRUAL_DAYS,
        build_monthly_payroll_notes,
        compute_monthly_ledger_amounts,
    )

    period_anchor = date(run.period_year, run.period_month, 1)
    line_list = list(run.lines.select_related('employee'))
    employee_ids = [ln.employee_id for ln in line_list]

    last_ledger_by_emp = {}
    if employee_ids:
        for lg in EmployeeLedger.objects.filter(
            employee_id__in=employee_ids,
            date__lt=period_anchor,
        ).order_by('employee_id', '-date', '-created_at'):
            if lg.employee_id not in last_ledger_by_emp:
                last_ledger_by_emp[lg.employee_id] = lg

    def _ids_from_breakdown(key: str) -> list:
        collected = []
        for ln in line_list:
            collected.extend(x['id'] for x in (ln.breakdown or {}).get(key, []))
        return collected

    absence_ids = _ids_from_breakdown('absences')
    if absence_ids:
        EmployeeAbsence.objects.filter(id__in=absence_ids).update(applied_to_payroll=run)

    leave_ids = _ids_from_breakdown('unpaid_leaves')
    if leave_ids:
        EmployeeLeave.objects.filter(id__in=leave_ids).update(applied_to_payroll=run)

    penalty_ids = _ids_from_breakdown('penalties')
    if penalty_ids:
        EmployeeStatement.objects.filter(id__in=penalty_ids).update(applied_to_payroll=run)

    loans_to_mark_paid = []
    loan_inst_ids = _ids_from_breakdown('loan_installments')
    if loan_inst_ids:
        LoanInstallment.objects.filter(id__in=loan_inst_ids).update(
            applied_to_payroll=run, status=LoanInstallment.Status.PAID,
        )
        inst_rows = list(
            LoanInstallment.objects.filter(id__in=loan_inst_ids).select_related('loan'),
        )
        loan_ids = {i.loan_id for i in inst_rows}
        if loan_ids:
            loans_with_pending = set(
                LoanInstallment.objects.filter(
                    loan_id__in=loan_ids,
                    status=LoanInstallment.Status.PENDING,
                ).values_list('loan_id', flat=True),
            )
            for inst in inst_rows:
                loan = inst.loan
                if (
                    loan.id not in loans_with_pending
                    and loan.status == EmployeeLoan.Status.ACTIVE
                ):
                    loans_to_mark_paid.append(loan)

    for line in line_list:
        sid = transaction.savepoint()
        try:
            last_ledger = last_ledger_by_emp.get(line.employee_id)

            prev_leave_days = last_ledger.cumulative_leave_days if last_ledger else Decimal('0')
            prev_leave_amt = last_ledger.cumulative_leave_amount if last_ledger else Decimal('0')
            prev_eosb = last_ledger.cumulative_eosb_amount if last_ledger else Decimal('0')

            leave_days_change = MONTHLY_LEAVE_ACCRUAL_DAYS
            calc = compute_monthly_ledger_amounts(
                gross_salary=line.gross_salary,
                hire_date=line.employee.hire_date,
                period_year=run.period_year,
                period_month=run.period_month,
            )
            leave_amount_change = calc['leave_amount']
            eosb_amount_change = calc['eosb']
            cum_leave_days = prev_leave_days + leave_days_change
            cum_leave_amt = prev_leave_amt + leave_amount_change
            cum_eosb = prev_eosb + eosb_amount_change

            notes = build_monthly_payroll_notes(
                period_year=run.period_year,
                period_month=run.period_month,
                month_days=salary_month_days(run.period_year, run.period_month),
                gross_salary=line.gross_salary,
                daily_rate=calc['daily_rate'],
                hire_date=line.employee.hire_date,
                prev_leave_days=prev_leave_days,
                prev_leave_amount=prev_leave_amt,
                prev_eosb=prev_eosb,
                leave_days_change=leave_days_change,
                leave_amount_change=leave_amount_change,
                eosb_amount_change=eosb_amount_change,
                cumulative_leave_days=cum_leave_days,
                cumulative_leave_amount=cum_leave_amt,
                cumulative_eosb=cum_eosb,
                payroll_run_id=run.id,
            )

            EmployeeLedger.objects.create(
                employee=line.employee,
                transaction_type=EmployeeLedger.TransactionType.MONTHLY_PAYROLL,
                date=calendar_month_last_day(run.period_year, run.period_month),
                leave_days_change=leave_days_change,
                leave_amount_change=leave_amount_change,
                eosb_amount_change=eosb_amount_change,
                cumulative_leave_days=cum_leave_days,
                cumulative_leave_amount=cum_leave_amt,
                cumulative_eosb_amount=cum_eosb,
                payroll_run=run,
                notes=notes,
                created_by=user
            )
            transaction.savepoint_commit(sid)
        except Exception:
            transaction.savepoint_rollback(sid)

    if loans_to_mark_paid:
        paid_ids = {ln.id for ln in loans_to_mark_paid}
        EmployeeLoan.objects.filter(
            id__in=paid_ids,
            status=EmployeeLoan.Status.ACTIVE,
        ).update(status=EmployeeLoan.Status.PAID)

    # تحديث حالة المسير إلى مُغلق
    run.status = PayrollRun.Status.LOCKED
    run.locked_at = timezone.now()
    run.locked_by = user
    run.save(update_fields=['status', 'locked_at', 'locked_by'])
    return run


# ══════════════════════════════════════════════════════════════════════════════
# 3. إلغاء الترحيل (فك القفل) — سوبر يوزر فقط
# ══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def unlock_payroll_run(run: PayrollRun, user):
    """
    يفك ربط كل بنود المسير ويعيده لحالة DRAFT.

    ⚠️ عملية حساسة:
      - الغيابات والإجازات والمخالفات → تعود لحالة "غير مُحتسبة"
      - أقساط السلف → تعود لحالة PENDING
      - السلف التي اكتملت → تعود لحالة ACTIVE

    يجب إعادة بناء المسير (Rebuild) بعد فك القفل.
    فحص الصلاحية (is_superuser) يتم في الـ View.
    """
    if run.status != PayrollRun.Status.LOCKED:
        raise ValueError('المسير ليس مغلقاً.')

    # فك ربط كل البنود
    EmployeeAbsence.objects.filter(applied_to_payroll=run).update(applied_to_payroll=None)
    EmployeeLeave.objects.filter(applied_to_payroll=run).update(applied_to_payroll=None)
    LoanInstallment.objects.filter(applied_to_payroll=run).update(
        applied_to_payroll=None, status=LoanInstallment.Status.PENDING
    )
    EmployeeStatement.objects.filter(applied_to_payroll=run).update(applied_to_payroll=None)

    # فك وحذف سجلات المخصصات (Ledger) التي تم إنشاؤها بهذا المسير
    sid = transaction.savepoint()
    try:
        from apps.employees.models import EmployeeLedger
        EmployeeLedger.objects.filter(payroll_run=run).delete()
        transaction.savepoint_commit(sid)
    except Exception:
        transaction.savepoint_rollback(sid)

    # إرجاع السلف التي أصبحت PAID بسبب آخر قسط في هذا المسير
    from apps.employees.models import EmployeeLoan
    affected_loan_ids = LoanInstallment.objects.filter(
        applied_to_payroll__isnull=True,        # أقساط فُكّ ربطها للتو
        loan__status=EmployeeLoan.Status.PAID,  # سلفتها مُعلَّمة مدفوعة
    ).values_list('loan_id', flat=True).distinct()

    if affected_loan_ids:
        loans_with_pending = set(
            LoanInstallment.objects.filter(
                loan_id__in=affected_loan_ids,
                status=LoanInstallment.Status.PENDING,
            ).values_list('loan_id', flat=True),
        )
        if loans_with_pending:
            EmployeeLoan.objects.filter(
                id__in=loans_with_pending,
                status=EmployeeLoan.Status.PAID,
            ).update(status=EmployeeLoan.Status.ACTIVE)

    # إعادة المسير لحالة مسودة
    run.status = PayrollRun.Status.DRAFT
    run.locked_at = None
    run.locked_by = None
    run.save(update_fields=['status', 'locked_at', 'locked_by'])
    return run
