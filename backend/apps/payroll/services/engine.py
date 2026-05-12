"""
خدمة حساب مسير الرواتب الشهري.

build_payroll_run(branch, year, month, user):
    - يبني/يحدّث مسير DRAFT للفرع والشهر المحدد.
    - يجمع الموظفين النشطين في الفرع.
    - لكل موظف يحسب:
        gross = basic + housing + transport + other + cash
        absence_deduction = من EmployeeAbsence (لم تُحتسب في مسير سابق)
        unpaid_leave_deduction = من EmployeeLeave نوع unpaid في الشهر
        loan_deduction = من LoanInstallment لنفس الشهر
        penalty_deduction = من EmployeeStatement نوع PENALTY في الشهر
        insurance_deduction = gross × insurance_deduction_rate / 100
    - يعيد إنشاء PayrollLine لكل موظف ولا يقفل البنود (تُقفل عند lock).

lock_payroll_run(run, user):
    - يربط كل بند خصم بهذا المسير (applied_to_payroll = run).
    - يحدّث LoanInstallment.status = PAID.
    - يقفل المسير ليصبح مرحَّلاً.

unlock_payroll_run(run, user):
    - فك الربط (للسوبر يوزر فقط) ويُرجع البنود لحالة قابلة للاحتساب.
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
    return Decimal(v or 0).quantize(Decimal('0.01'))


@transaction.atomic
def build_payroll_run(branch, year: int, month: int, user=None):
    """يبني/يعيد بناء مسير DRAFT لفرع وشهر محددين."""
    run, _ = PayrollRun.objects.get_or_create(
        branch=branch, period_year=year, period_month=month,
        defaults={'created_by': user, 'status': PayrollRun.Status.DRAFT}
    )
    if run.status == PayrollRun.Status.LOCKED:
        raise ValueError('المسير مُغلق ولا يمكن إعادة بنائه. أعد فتحه أولاً.')

    # قفل صف على المسير لمنع أي بناء مواز لنفس (الفرع/السنة/الشهر)
    PayrollRun.objects.select_for_update().filter(pk=run.pk).first()

    # امسح الأسطر القديمة فعلياً لتفادي تعارض القيد الفريد (BaseModel.objects.delete = soft)
    PayrollLine.all_objects.filter(run=run).delete()

    month_days = monthrange(year, month)[1]
    period_start = date(year, month, 1)
    period_end = date(year, month, month_days)

    employees = Employee.objects.filter(
        branch=branch, status=Employee.Status.ACTIVE
    ).order_by('name').distinct()

    seen_ids = set()
    for emp in employees:
        if emp.id in seen_ids:
            continue
        seen_ids.add(emp.id)
        # دفاعياً: hard-delete أي سطر قديم لنفس الموظف في هذا المسير
        PayrollLine.all_objects.filter(run=run, employee=emp).delete()
        line = PayrollLine(
            run=run, employee=emp,
            basic_salary=emp.basic_salary or 0,
            housing_allowance=emp.housing_allowance or 0,
            transport_allowance=emp.transport_allowance or 0,
            other_allowance=emp.other_allowance or 0,
            cash_amount=emp.cash_amount or 0,
            month_days=month_days,
        )
        gross = (
            Decimal(emp.basic_salary or 0)
            + Decimal(emp.housing_allowance or 0)
            + Decimal(emp.transport_allowance or 0)
            + Decimal(emp.other_allowance or 0)
            + Decimal(emp.cash_amount or 0)
        )
        line.daily_rate = (gross / Decimal(month_days)).quantize(Decimal('0.01')) if month_days else Decimal('0')

        # ── الغياب ─────────────────────────────────────────
        absences = EmployeeAbsence.objects.filter(
            employee=emp,
            absence_date__range=(period_start, period_end),
        ).filter(Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll=run))
        abs_days = sum((a.days for a in absences), 0)
        abs_ded = sum((Decimal(a.deduction_amount or 0) for a in absences), Decimal('0'))
        line.absence_days = abs_days
        line.absence_deduction = _q(abs_ded)

        # ── الإجازة بدون راتب ──────────────────────────────
        unpaid_leaves = EmployeeLeave.objects.filter(
            employee=emp,
            leave_type=EmployeeLeave.LeaveType.UNPAID,
            date_from__lte=period_end,
            date_to__gte=period_start,
        ).filter(Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll=run))
        unpaid_days = Decimal('0')
        for lv in unpaid_leaves:
            # احسب التقاطع مع الشهر فقط
            s = max(lv.date_from, period_start)
            e = min(lv.date_to, period_end)
            if e >= s:
                unpaid_days += Decimal((e - s).days + 1)
        line.unpaid_leave_days = unpaid_days
        line.unpaid_leave_deduction = _q(line.daily_rate * unpaid_days)

        # ── أقساط السلفة ───────────────────────────────────
        installments = LoanInstallment.objects.filter(
            loan__employee=emp,
            period_year=year, period_month=month,
            status=LoanInstallment.Status.PENDING,
        ).filter(Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll=run))
        loan_ded = sum((Decimal(i.amount) for i in installments), Decimal('0'))
        line.loan_deduction = _q(loan_ded)

        # ── المخالفات ──────────────────────────────────────
        penalties = EmployeeStatement.objects.filter(
            employee=emp,
            statement_type=EmployeeStatement.StatementType.PENALTY,
            statement_date__range=(period_start, period_end),
        ).filter(Q(applied_to_payroll__isnull=True) | Q(applied_to_payroll=run))
        pen_ded = sum((Decimal(p.deduction_amount or 0) for p in penalties), Decimal('0'))
        line.penalty_deduction = _q(pen_ded)

        # ── التأمينات ──────────────────────────────────────
        rate = Decimal(emp.insurance_deduction_rate or 0)
        line.insurance_deduction = _q(gross * rate / Decimal('100'))

        # ── التفاصيل ───────────────────────────────────────
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

        line.compute_totals()
        line.save()

    run.recompute_totals()
    return run


@transaction.atomic
def lock_payroll_run(run: PayrollRun, user):
    """يقفل المسير ويربط كل بنوده (idempotency)."""
    if run.status == PayrollRun.Status.LOCKED:
        raise ValueError('المسير مُغلق بالفعل.')

    for line in run.lines.select_related('employee'):
        bd = line.breakdown or {}
        # ربط الغيابات
        ids = [x['id'] for x in bd.get('absences', [])]
        if ids:
            EmployeeAbsence.objects.filter(id__in=ids).update(applied_to_payroll=run)
        # ربط الإجازات بدون راتب
        ids = [x['id'] for x in bd.get('unpaid_leaves', [])]
        if ids:
            EmployeeLeave.objects.filter(id__in=ids).update(applied_to_payroll=run)
        # ربط أقساط السلف + تحديث الحالة
        ids = [x['id'] for x in bd.get('loan_installments', [])]
        if ids:
            LoanInstallment.objects.filter(id__in=ids).update(
                applied_to_payroll=run, status=LoanInstallment.Status.PAID
            )
            # حدّث حالة السلفة إن اكتمل سدادها
            from apps.employees.models import EmployeeLoan
            for inst in LoanInstallment.objects.filter(id__in=ids).select_related('loan'):
                loan = inst.loan
                if not loan.installments_log.filter(status=LoanInstallment.Status.PENDING).exists():
                    if loan.status == EmployeeLoan.Status.ACTIVE:
                        loan.status = EmployeeLoan.Status.PAID
                        loan.save(update_fields=['status'])
        # ربط المخالفات
        ids = [x['id'] for x in bd.get('penalties', [])]
        if ids:
            EmployeeStatement.objects.filter(id__in=ids).update(applied_to_payroll=run)

    run.status = PayrollRun.Status.LOCKED
    run.locked_at = timezone.now()
    run.locked_by = user
    run.save(update_fields=['status', 'locked_at', 'locked_by'])
    return run


@transaction.atomic
def unlock_payroll_run(run: PayrollRun, user):
    """فك ربط بنود المسير ليُعاد بناؤه (سوبر يوزر فقط — يُتحقق في الـ view)."""
    if run.status != PayrollRun.Status.LOCKED:
        raise ValueError('المسير ليس مغلقاً.')

    EmployeeAbsence.objects.filter(applied_to_payroll=run).update(applied_to_payroll=None)
    EmployeeLeave.objects.filter(applied_to_payroll=run).update(applied_to_payroll=None)
    LoanInstallment.objects.filter(applied_to_payroll=run).update(
        applied_to_payroll=None, status=LoanInstallment.Status.PENDING
    )
    EmployeeStatement.objects.filter(applied_to_payroll=run).update(applied_to_payroll=None)

    # لو كانت سلفة قد أصبحت PAID بسبب آخر قسط في هذا المسير، أعدها ACTIVE
    from apps.employees.models import EmployeeLoan
    for loan in EmployeeLoan.objects.filter(installments_log__loan__isnull=False).distinct():
        if loan.installments_log.filter(status=LoanInstallment.Status.PENDING).exists() \
                and loan.status == EmployeeLoan.Status.PAID:
            loan.status = EmployeeLoan.Status.ACTIVE
            loan.save(update_fields=['status'])

    run.status = PayrollRun.Status.DRAFT
    run.locked_at = None
    run.locked_by = None
    run.save(update_fields=['status', 'locked_at', 'locked_by'])
    return run
