"""
محرك حساب مسير الرواتب الشهري — Payroll Engine
=================================================
هذا الملف هو قلب نظام الرواتب. يحتوي على 3 دوال رئيسية:

1. build_payroll_run(branch, year, month, user)
   ────────────────────────────────────────────
   يبني/يعيد بناء مسير DRAFT لفرع وشهر محددين.
   لكل موظف نشط أو في إجازة:
     - يحسب الراتب الإجمالي = أساسي + سكن + نقل + إضافي + كاش
     - يحسب خصم الغياب من سجلات EmployeeAbsence
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
from decimal import Decimal
from calendar import monthrange
from datetime import date
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.payroll.models import PayrollRun, PayrollLine
from apps.employees.models import (
    Employee, EmployeeAbsence, EmployeeLeave, EmployeeStatement, LoanInstallment
)


def _q(v):
    """تقريب القيمة لرقمين عشريين (لمنع أخطاء الكسور)."""
    return Decimal(v or 0).quantize(Decimal('0.01'))


# ══════════════════════════════════════════════════════════════════════════════
# 1. بناء المسير
# ══════════════════════════════════════════════════════════════════════════════

def _employees_for_payroll_run(branch, salary_mode, *, sponsorship_id=None):
    """موظفون نشطون/في إجازة حسب نوع الراتب وشركة الكفالة."""
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

    # ── حساب حدود الشهر ──
    month_days = monthrange(year, month)[1]                # عدد أيام الشهر
    period_start = date(year, month, 1)                     # أول يوم
    period_end = date(year, month, month_days)               # آخر يوم

    # ── جلب الموظفين حسب نوع الراتب ──
    employees = _employees_for_payroll_run(
        branch, salary_mode, sponsorship_id=sponsorship_id,
    ).order_by('name').distinct()

    seen_ids = set()  # لمنع تكرار الموظف (حماية إضافية)

    for emp in employees:
        if emp.id in seen_ids:
            continue
        seen_ids.add(emp.id)

        # ── حماية النقل نصف الشهر ─────────────────────────────
        # إذا الموظف مُحتسب في مسير LOCKED لفرع آخر لنفس الشهر → تخطّي
        # هذا يمنع ازدواج الراتب عند النقل بين الفروع خلال الشهر
        already_in_locked = PayrollLine.objects.filter(
            employee=emp,
            run__period_year=year,
            run__period_month=month,
            run__status=PayrollRun.Status.LOCKED,
        ).exclude(run=run).exists()
        if already_in_locked:
            # الموظف محسوب في مسير مُرحَّل لفرع آخر — لا نحسبه مرتين
            PayrollLine.all_objects.filter(run=run, employee=emp).delete()
            continue

        # حذف أي سطر قديم لنفس الموظف (حماية من القيد الفريد)
        PayrollLine.all_objects.filter(run=run, employee=emp).delete()

        # ── إنشاء سطر جديد بالراتب الأساسي ──
        line = PayrollLine(
            run=run, employee=emp,
            basic_salary=emp.basic_salary or 0,
            housing_allowance=emp.housing_allowance or 0,
            transport_allowance=emp.transport_allowance or 0,
            other_allowance=emp.other_allowance or 0,
            cash_amount=emp.cash_amount or 0,
            meal_allowance=emp.meal_allowance or 0,
            month_days=month_days,
        )

        # الراتب الإجمالي (قبل الخصومات)
        gross = (
            Decimal(emp.basic_salary or 0)
            + Decimal(emp.housing_allowance or 0)
            + Decimal(emp.transport_allowance or 0)
            + Decimal(emp.other_allowance or 0)
            + Decimal(emp.cash_amount or 0)
            + Decimal(emp.meal_allowance or 0)
        )

        # المعدل اليومي (يُستخدم لحساب خصم الإجازة بدون راتب)
        line.daily_rate = (gross / Decimal(month_days)).quantize(Decimal('0.01')) if month_days else Decimal('0')

        # ── حساب خصم الغياب ──────────────────────────────────
        # يجلب الغيابات في هذا الشهر التي لم تُحتسب في مسير آخر (أو محتسبة في هذا المسير)
        absences = EmployeeAbsence.objects.filter(
            employee=emp,
            absence_date__range=(period_start, period_end),
        ).filter(Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll=run))
        abs_days = sum((a.days for a in absences), 0)
        abs_ded = sum((Decimal(a.deduction_amount or 0) for a in absences), Decimal('0'))
        line.absence_days = abs_days
        line.absence_deduction = _q(abs_ded)

        # ── حساب خصم الإجازة بدون راتب ──────────────────────
        # يحسب فقط الأيام المتقاطعة مع هذا الشهر
        unpaid_leaves = EmployeeLeave.objects.filter(
            employee=emp,
            leave_type=EmployeeLeave.LeaveType.UNPAID,
            date_from__lte=period_end,
            date_to__gte=period_start,
        ).filter(Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll=run))
        unpaid_days = Decimal('0')
        for lv in unpaid_leaves:
            # حساب التقاطع: الأيام المشتركة بين الإجازة وحدود الشهر
            s = max(lv.date_from, period_start)
            e = min(lv.date_to, period_end)
            if e >= s:
                unpaid_days += Decimal((e - s).days + 1)
        line.unpaid_leave_days = unpaid_days
        line.unpaid_leave_deduction = _q(line.daily_rate * unpaid_days)

        # ── حساب خصم أقساط السلف ────────────────────────────
        # يجلب الأقساط المستحقة لهذا الشهر والمعلّقة (PENDING)
        installments = LoanInstallment.objects.filter(
            loan__employee=emp,
            period_year=year, period_month=month,
            status=LoanInstallment.Status.PENDING,
        ).filter(Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll=run))
        loan_ded = sum((Decimal(i.amount) for i in installments), Decimal('0'))
        line.loan_deduction = _q(loan_ded)

        # ── حساب خصم المخالفات ───────────────────────────────
        # يجلب المخالفات (إنذارات مالية) في هذا الشهر
        penalties = EmployeeStatement.objects.filter(
            employee=emp,
            statement_type=EmployeeStatement.StatementType.PENALTY,
            statement_date__range=(period_start, period_end),
        ).filter(Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll=run))
        pen_ded = sum((Decimal(p.deduction_amount or 0) for p in penalties), Decimal('0'))
        line.penalty_deduction = _q(pen_ded)

        # ── حساب خصم التأمينات ───────────────────────────────
        rate = Decimal(emp.insurance_deduction_rate or 0)
        line.insurance_deduction = _q(gross * rate / Decimal('100'))

        # ── حفظ تفاصيل الخصومات (للتتبع عند الترحيل) ────────
        line.breakdown = {
            'absences': [
                {'id': a.id, 'date': a.absence_date.isoformat(), 'days': a.days,
                 'amount': str(a.deduction_amount)} for a in absences
            ],
            'unpaid_leaves': [
                {'id': l.id, 'from': l.date_from.isoformat(), 'to': l.date_to.isoformat()}
                for l in unpaid_leaves
            ],
            'loan_installments': [
                {'id': i.id, 'loan_id': i.loan_id, 'amount': str(i.amount)}
                for i in installments
            ],
            'penalties': [
                {'id': p.id, 'title': p.title, 'amount': str(p.deduction_amount)}
                for p in penalties
            ],
            'insurance_rate': str(rate),
        }

        # حساب الإجماليات (استحقاقات − خصومات = صافي)
        line.compute_totals()
        line.save()

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

    for line in run.lines.select_related('employee'):
        bd = line.breakdown or {}

        # ربط الغيابات بهذا المسير
        ids = [x['id'] for x in bd.get('absences', [])]
        if ids:
            EmployeeAbsence.objects.filter(id__in=ids).update(applied_to_payroll=run)

        # ربط الإجازات بدون راتب بهذا المسير
        ids = [x['id'] for x in bd.get('unpaid_leaves', [])]
        if ids:
            EmployeeLeave.objects.filter(id__in=ids).update(applied_to_payroll=run)

        # ربط أقساط السلف + تعليمها كمدفوعة
        ids = [x['id'] for x in bd.get('loan_installments', [])]
        if ids:
            LoanInstallment.objects.filter(id__in=ids).update(
                applied_to_payroll=run, status=LoanInstallment.Status.PAID
            )
            # فحص: هل اكتملت كل أقساط السلفة؟ إذا نعم → حدّث حالة السلفة لـ PAID
            from apps.employees.models import EmployeeLoan
            for inst in LoanInstallment.objects.filter(id__in=ids).select_related('loan'):
                loan = inst.loan
                if not loan.installments_log.filter(status=LoanInstallment.Status.PENDING).exists():
                    if loan.status == EmployeeLoan.Status.ACTIVE:
                        loan.status = EmployeeLoan.Status.PAID
                        loan.save(update_fields=['status'])

        # ربط المخالفات بهذا المسير
        ids = [x['id'] for x in bd.get('penalties', [])]
        if ids:
            EmployeeStatement.objects.filter(id__in=ids).update(applied_to_payroll=run)

        # ── إنشاء سجل المخصصات (Ledger) لهذا الشهر ──
        sid = transaction.savepoint()
        try:
            from apps.employees.models import EmployeeLedger
            from apps.employees.services.accrual_ledger_notes import (
                MONTHLY_LEAVE_ACCRUAL_DAYS,
                build_monthly_payroll_notes,
                compute_monthly_ledger_amounts,
            )

            last_ledger = EmployeeLedger.objects.filter(
                employee=line.employee,
                date__lt=date(run.period_year, run.period_month, 1)
            ).order_by('-date', '-created_at').first()

            prev_leave_days = last_ledger.cumulative_leave_days if last_ledger else Decimal('0')
            prev_leave_amt = last_ledger.cumulative_leave_amount if last_ledger else Decimal('0')
            prev_eosb = last_ledger.cumulative_eosb_amount if last_ledger else Decimal('0')

            leave_days_change = MONTHLY_LEAVE_ACCRUAL_DAYS
            calc = compute_monthly_ledger_amounts(
                gross_salary=line.gross_salary,
                daily_rate=line.daily_rate,
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
                month_days=line.month_days or monthrange(run.period_year, run.period_month)[1],
                gross_salary=line.gross_salary,
                daily_rate=line.daily_rate,
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
                date=date(run.period_year, run.period_month, monthrange(run.period_year, run.period_month)[1]),
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

    for loan in EmployeeLoan.objects.filter(id__in=affected_loan_ids):
        # إذا عاد لها أقساط معلّقة → أعد الحالة لـ ACTIVE
        if loan.installments_log.filter(status=LoanInstallment.Status.PENDING).exists():
            loan.status = EmployeeLoan.Status.ACTIVE
            loan.save(update_fields=['status'])

    # إعادة المسير لحالة مسودة
    run.status = PayrollRun.Status.DRAFT
    run.locked_at = None
    run.locked_by = None
    run.save(update_fields=['status', 'locked_at', 'locked_by'])
    return run
