"""تقرير التحقق المالي لمسير الرواتب قبل الإغلاق النهائي."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from apps.payroll.models import PayrollRun
from apps.payroll.services.payroll_line_columns import payroll_lines_select_related
from apps.payroll.services.period_eligibility import employee_payroll_period, prorate_amount

_TOLERANCE = Decimal('0.02')


@dataclass
class AuditCheck:
    code: str
    title: str
    level: str  # ok | warn | error
    detail: str
    run_label: str = ''
    employee_name: str = ''


@dataclass
class PayrollFinancialAudit:
    checks: list[AuditCheck] = field(default_factory=list)
    employees_count: int = 0
    total_earnings: Decimal = Decimal('0')
    total_deductions: Decimal = Decimal('0')
    total_net: Decimal = Decimal('0')
    runs_count: int = 0
    error_count: int = 0
    warn_count: int = 0
    ok_count: int = 0

    @property
    def ready_to_lock(self) -> bool:
        return self.error_count == 0 and self.employees_count > 0

    @property
    def status_level(self) -> str:
        if self.error_count:
            return 'error'
        if self.warn_count:
            return 'warn'
        if self.employees_count == 0:
            return 'warn'
        return 'ok'

    @property
    def status_label(self) -> str:
        labels = {
            'error': 'يوجد أخطاء — لا يُنصح بالإغلاق',
            'warn': 'جاهز مع ملاحظات',
            'ok': 'جاهز للإغلاق النهائي',
        }
        return labels[self.status_level]


def _q(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal('0.01'))


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= _TOLERANCE


def _add_check(audit: PayrollFinancialAudit, check: AuditCheck) -> None:
    audit.checks.append(check)
    if check.level == 'error':
        audit.error_count += 1
    elif check.level == 'warn':
        audit.warn_count += 1
    else:
        audit.ok_count += 1


def _run_label(run: PayrollRun) -> str:
    if run.run_kind == PayrollRun.RunKind.CONSOLIDATED:
        name = run.company.name if run.company_id else 'موحّد'
        return f'{name} — {run.period_label}'
    if run.run_kind == PayrollRun.RunKind.DETAILED:
        name = run.company.name if run.company_id else 'تفصيلي'
        return f'{name} — تفصيلي {run.period_label}'
    branch = run.branch.name if run.branch_id else '—'
    return f'{branch} — {run.period_label}'


def _expected_insurance(emp, year: int, month: int) -> Decimal:
    period = employee_payroll_period(
        period_year=year,
        period_month=month,
        hire_date=getattr(emp, 'hire_date', None),
        end_date=getattr(emp, 'end_date', None),
    )
    base_full = Decimal(emp.basic_salary or 0) + Decimal(emp.housing_allowance or 0)
    insurance_base = prorate_amount(
        base_full,
        period['payable_base_days'],
        period['month_days'],
    )
    rate = min(max(Decimal(emp.insurance_deduction_rate or 0), Decimal('0')), Decimal('100'))
    return _q(insurance_base * rate / Decimal('100'))


def _lines_for_run(run: PayrollRun) -> list:
    prefetched = getattr(run, '_prefetched_objects_cache', {}).get('lines')
    if prefetched is not None:
        return sorted(
            prefetched,
            key=lambda line: (line.employee.name if line.employee_id else ''),
        )
    return list(payroll_lines_select_related(run.lines).order_by('employee__name'))


def _audit_standard_run(audit: PayrollFinancialAudit, run: PayrollRun) -> None:
    label = _run_label(run)
    lines = _lines_for_run(run)

    if not lines:
        _add_check(audit, AuditCheck(
            code='empty_run',
            title='مسير بدون موظفين',
            level='warn',
            detail='لا توجد أسطر راتب في هذه المسودة.',
            run_label=label,
        ))
        return

    sum_earn = sum(_q(line.total_earnings) for line in lines)
    sum_deduct = sum(_q(line.total_deductions) for line in lines)
    sum_net = sum(_q(line.net_salary) for line in lines)

    if not _close(sum_earn, run.total_earnings):
        _add_check(audit, AuditCheck(
            code='run_earnings_mismatch',
            title='تعارض إجمالي الاستحقاقات',
            level='error',
            detail=f'مجموع الأسطر {sum_earn} ≠ رأس المسير {run.total_earnings}',
            run_label=label,
        ))
    else:
        _add_check(audit, AuditCheck(
            code='run_earnings_ok',
            title='إجمالي الاستحقاقات',
            level='ok',
            detail=f'مجموع الأسطر يطابق رأس المسير ({sum_earn} ر.س)',
            run_label=label,
        ))

    if not _close(sum_deduct, run.total_deductions):
        _add_check(audit, AuditCheck(
            code='run_deductions_mismatch',
            title='تعارض إجمالي الخصومات',
            level='error',
            detail=f'مجموع الأسطر {sum_deduct} ≠ رأس المسير {run.total_deductions}',
            run_label=label,
        ))
    else:
        _add_check(audit, AuditCheck(
            code='run_deductions_ok',
            title='إجمالي الخصومات',
            level='ok',
            detail=f'مجموع الأسطر يطابق رأس المسير ({sum_deduct} ر.س)',
            run_label=label,
        ))

    if not _close(sum_net, run.total_net):
        _add_check(audit, AuditCheck(
            code='run_net_mismatch',
            title='تعارض الصافي الكلي',
            level='error',
            detail=f'مجموع الأسطر {sum_net} ≠ رأس المسير {run.total_net}',
            run_label=label,
        ))
    else:
        _add_check(audit, AuditCheck(
            code='run_net_ok',
            title='الصافي الكلي',
            level='ok',
            detail=f'مجموع الأسطر يطابق رأس المسير ({sum_net} ر.س)',
            run_label=label,
        ))

    if run.employees_count != len(lines):
        _add_check(audit, AuditCheck(
            code='employee_count_mismatch',
            title='عدد الموظفين',
            level='error',
            detail=f'العداد في المسير {run.employees_count} ≠ عدد الأسطر {len(lines)}',
            run_label=label,
        ))

    for line in lines:
        emp = line.employee
        emp_name = emp.name or f'#{emp.pk}'

        calc_net = _q(line.total_earnings) - _q(line.total_deductions)
        if not _close(calc_net, line.net_salary):
            _add_check(audit, AuditCheck(
                code='line_net_formula',
                title='معادلة الصافي',
                level='error',
                detail=(
                    f'الاستحقاقات {_q(line.total_earnings)} − الخصومات {_q(line.total_deductions)} '
                    f'= {calc_net} ≠ المسجّل {_q(line.net_salary)}'
                ),
                run_label=label,
                employee_name=emp_name,
            ))

        if line.net_salary < 0:
            _add_check(audit, AuditCheck(
                code='negative_net',
                title='صافي سالب',
                level='error',
                detail=f'الصافي {_q(line.net_salary)} ر.س',
                run_label=label,
                employee_name=emp_name,
            ))

        calc_deduct = _q(
            line.absence_deduction
            + line.unpaid_leave_deduction
            + line.loan_deduction
            + line.penalty_deduction
            + line.insurance_deduction
            + line.other_deduction
        )
        if not _close(calc_deduct, line.total_deductions):
            _add_check(audit, AuditCheck(
                code='deductions_breakdown',
                title='تفصيل الخصومات',
                level='error',
                detail=f'مجموع البنود {calc_deduct} ≠ الإجمالي {_q(line.total_deductions)}',
                run_label=label,
                employee_name=emp_name,
            ))

        expected_ins = _expected_insurance(emp, run.period_year, run.period_month)
        if not _close(expected_ins, line.insurance_deduction):
            rate = emp.insurance_deduction_rate or 0
            _add_check(audit, AuditCheck(
                code='insurance_base',
                title='خصم التأمينات (أساسي + سكن)',
                level='error',
                detail=(
                    f'المتوقع {expected_ins} ر.س ({rate}% من أساسي+سكن) '
                    f'≠ المسجّل {_q(line.insurance_deduction)} ر.س'
                ),
                run_label=label,
                employee_name=emp_name,
            ))


def _audit_detailed_run(audit: PayrollFinancialAudit, run: PayrollRun) -> None:
    label = _run_label(run)
    rows = list(
        run.allocation_lines.select_related('employee', 'branch').order_by('employee__name', 'id'),
    )
    if not rows:
        _add_check(audit, AuditCheck(
            code='detailed_empty',
            title='مسير تفصيلي فارغ',
            level='warn',
            detail='لا يوجد موظفون منقولون في هذه الفترة.',
            run_label=label,
        ))
        return

    bearing = [r for r in rows if r.bears_salary]
    sum_net = sum(_q(r.net_amount) for r in bearing)
    if not _close(sum_net, run.total_net):
        _add_check(audit, AuditCheck(
            code='detailed_net_mismatch',
            title='صافي المسير التفصيلي',
            level='error',
            detail=f'مجموع الفروع المتحمّلة {sum_net} ≠ رأس المسير {_q(run.total_net)}',
            run_label=label,
        ))
    else:
        _add_check(audit, AuditCheck(
            code='detailed_net_ok',
            title='صافي التوزيع التفصيلي',
            level='ok',
            detail=f'مجموع الفروع المتحمّلة يطابق رأس المسير ({sum_net} ر.س)',
            run_label=label,
        ))

    transferred = {r.employee_id for r in rows}
    if run.employees_count != len(transferred):
        _add_check(audit, AuditCheck(
            code='detailed_employee_count',
            title='عدد المنقولين',
            level='error',
            detail=f'العداد {run.employees_count} ≠ الموظفون الفريدون {len(transferred)}',
            run_label=label,
        ))

    for row in rows:
        if row.bears_salary and row.net_amount < 0:
            _add_check(audit, AuditCheck(
                code='detailed_negative',
                title='مبلغ فرع سالب',
                level='error',
                detail=f'{row.branch.name}: {_q(row.net_amount)} ر.س',
                run_label=label,
                employee_name=row.employee.name,
            ))
        if not row.bears_salary and row.net_amount != 0:
            _add_check(audit, AuditCheck(
                code='detailed_old_branch',
                title='الفرع السابق يجب أن يكون صفراً',
                level='error',
                detail=f'{row.branch.name}: {_q(row.net_amount)} ر.س (المتوقع 0)',
                run_label=label,
                employee_name=row.employee.name,
            ))


def audit_payroll_runs(runs) -> PayrollFinancialAudit:
    """يُنشئ تقرير تحقق مالي لمسودات المسير قبل الإغلاق."""
    audit = PayrollFinancialAudit()
    draft_runs = [
        r for r in runs
        if r.status == PayrollRun.Status.DRAFT
    ]
    audit.runs_count = len(draft_runs)
    audit.employees_count = sum(int(r.employees_count or 0) for r in draft_runs)
    audit.total_earnings = sum(_q(r.total_earnings) for r in draft_runs)
    audit.total_deductions = sum(_q(r.total_deductions) for r in draft_runs)
    audit.total_net = sum(_q(r.total_net) for r in draft_runs)

    if not draft_runs:
        _add_check(audit, AuditCheck(
            code='no_drafts',
            title='لا توجد مسودات',
            level='warn',
            detail='لا يوجد مسير مسودة للتحقق منه.',
        ))
        return audit

    for run in draft_runs:
        if run.run_kind == PayrollRun.RunKind.DETAILED:
            _audit_detailed_run(audit, run)
        else:
            _audit_standard_run(audit, run)

    if audit.error_count == 0 and audit.employees_count > 0:
        _add_check(audit, AuditCheck(
            code='lock_ready',
            title='التحقق المالي',
            level='ok',
            detail=(
                f'{audit.employees_count} موظف — '
                f'استحقاقات {audit.total_earnings} — '
                f'خصومات {audit.total_deductions} — '
                f'صافي {audit.total_net} ر.س'
            ),
        ))

    return audit
