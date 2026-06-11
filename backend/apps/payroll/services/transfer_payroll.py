"""
قواعد نقل الموظف في مسير الرواتب + بناء المسير التفصيلي.
────────────────────────────────────────────────────────
• نقل في منتصف الشهر (أو قبل إصدار المسير): الراتب كامل على الفرع الجديد.
• المسير العادي (standard): الموظف في مسير الفرع الجديد فقط براتب كامل.
• المسير التفصيلي (detailed): يوضح لكل فرع أيام التواجد ومبلغ التحمّل (قديم=0، جديد=كامل).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from apps.core.models import Branch
from apps.core.salary_month import calendar_period_bounds
from apps.employees.models import Employee, EmployeeStatement
from apps.payroll.models import PayrollAllocationLine, PayrollLine, PayrollRun


@dataclass(frozen=True)
class TransferEvent:
    employee_id: int
    statement_id: int
    transfer_date: date
    from_branch_id: int | None
    to_branch_id: int | None
    from_branch_name: str
    to_branch_name: str


def _parse_transfer_content(stmt: EmployeeStatement, company_id: int) -> TransferEvent | None:
    try:
        data = json.loads(stmt.content or '{}')
    except (json.JSONDecodeError, TypeError):
        return None
    if not data.get('branch_changed'):
        return None

    transfer_date = stmt.statement_date
    from_id = data.get('branch_from_id')
    to_id = data.get('branch_to_id')
    from_name = (data.get('branch_from') or '').strip()
    to_name = (data.get('branch_to') or '').strip()

    if not from_id and from_name and from_name != '—':
        br = Branch.objects.filter(company_id=company_id, name=from_name, is_active=True).first()
        from_id = br.id if br else None
    if not to_id and to_name and to_name != '—':
        br = Branch.objects.filter(company_id=company_id, name=to_name, is_active=True).first()
        to_id = br.id if br else None

    if not to_id or (from_id and from_id == to_id):
        return None
    return TransferEvent(
        employee_id=stmt.employee_id,
        statement_id=stmt.id,
        transfer_date=transfer_date,
        from_branch_id=from_id,
        to_branch_id=to_id,
        from_branch_name=from_name or '—',
        to_branch_name=to_name or '—',
    )


def transfers_in_period(company_id: int, year: int, month: int) -> dict[int, TransferEvent]:
    """آخر نقل بين فروع لكل موظف داخل الشهر."""
    period_start, period_end = calendar_period_bounds(year, month)
    stmts = (
        EmployeeStatement.objects.filter(
            employee__branch__company_id=company_id,
            statement_type=EmployeeStatement.StatementType.TRANSFER,
            statement_date__range=(period_start, period_end),
        )
        .select_related('employee')
        .order_by('employee_id', 'statement_date', 'id')
    )
    result: dict[int, TransferEvent] = {}
    for stmt in stmts:
        evt = _parse_transfer_content(stmt, company_id)
        if evt:
            result[evt.employee_id] = evt
    return result


def _employee_matches_salary_mode(
    emp: Employee,
    salary_mode: str,
    sponsorship_scope_ids: list[int] | None = None,
) -> bool:
    if salary_mode == PayrollRun.SalaryMode.CASH:
        return emp.sponsorship_id is None
    if salary_mode == PayrollRun.SalaryMode.TRANSFER:
        if emp.sponsorship_id is None:
            return False
        if sponsorship_scope_ids is not None:
            return emp.sponsorship_id in sponsorship_scope_ids
        return True
    return False


def _purge_other_detailed_draft_runs(
    *,
    company_id: int,
    year: int,
    month: int,
    salary_mode: str,
    keep_pk: int,
) -> None:
    """مسودة تفصيلية واحدة لكل شركة/فترة — حذف المسودات القديمة المجزّأة."""
    PayrollRun.objects.filter(
        company_id=company_id,
        period_year=year,
        period_month=month,
        salary_mode=salary_mode,
        run_kind=PayrollRun.RunKind.DETAILED,
        status=PayrollRun.Status.DRAFT,
    ).exclude(pk=keep_pk).delete()


def consolidate_detailed_draft_runs(
    *,
    company_ids,
    year: int,
    month: int,
    salary_mode: str,
) -> None:
    """الإبقاء على مسودة تفصيلية واحدة لكل شركة — حذف أي مسودات مكررة."""
    for company_id in company_ids:
        drafts = list(
            PayrollRun.objects.filter(
                company_id=company_id,
                period_year=year,
                period_month=month,
                salary_mode=salary_mode,
                run_kind=PayrollRun.RunKind.DETAILED,
                status=PayrollRun.Status.DRAFT,
            ).order_by('-updated_at', '-id'),
        )
        if len(drafts) <= 1:
            continue
        keeper = next((r for r in drafts if r.sponsorship_id is None), drafts[0])
        PayrollRun.objects.filter(
            pk__in=[r.pk for r in drafts if r.pk != keeper.pk],
        ).delete()


def _days_before_transfer(period_start: date, transfer_date: date) -> Decimal:
    if transfer_date <= period_start:
        return Decimal('0')
    return Decimal((transfer_date - period_start).days)


def _days_after_transfer(period_end: date, transfer_date: date) -> Decimal:
    if transfer_date > period_end:
        return Decimal('0')
    return Decimal((period_end - transfer_date).days + 1)


def employees_queryset_for_branch_payroll(
    branch: Branch,
    salary_mode: str,
    *,
    sponsorship_id: int | None,
    year: int,
    month: int,
    transfers=None,
):
    """
    موظفون يدخلون مسير الفرع:
    - الحاليون على الفرع (نشط / إجازة) ومطابقون لنوع الراتب
    - المنقولون إلى الفرع خلال الشهر (راتب كامل)
    - استبعاد المنقولين من الفرع خلال الشهر (حتى لو تأخر تحديث الفرع)
    """
    company_id = branch.company_id
    if transfers is None:
        transfers = transfers_in_period(company_id, year, month)

    period_start, period_end = calendar_period_bounds(year, month)
    base_qs = Employee.objects.filter(
        branch=branch,
        status__in=[Employee.Status.ACTIVE, Employee.Status.LEAVE],
    ).filter(
        Q(hire_date__isnull=True) | Q(hire_date__lte=period_end),
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=period_start),
    )
    if salary_mode == PayrollRun.SalaryMode.CASH:
        base_qs = base_qs.filter(sponsorship__isnull=True)
    elif salary_mode == PayrollRun.SalaryMode.TRANSFER:
        base_qs = base_qs.filter(sponsorship__isnull=False)
        if sponsorship_id:
            base_qs = base_qs.filter(sponsorship_id=sponsorship_id)
    else:
        raise ValueError('نوع الراتب غير صالح.')

    exclude_ids = set()
    include_ids = set()
    for emp_id, evt in transfers.items():
        if evt.from_branch_id == branch.id:
            exclude_ids.add(emp_id)
        if evt.to_branch_id == branch.id:
            include_ids.add(emp_id)

    if include_ids:
        extra = Employee.objects.filter(
            id__in=include_ids,
            status__in=[Employee.Status.ACTIVE, Employee.Status.LEAVE],
        )
        if salary_mode == PayrollRun.SalaryMode.CASH:
            extra = extra.filter(sponsorship__isnull=True)
        else:
            extra = extra.filter(sponsorship__isnull=False)
            if sponsorship_id:
                extra = extra.filter(sponsorship_id=sponsorship_id)
        base_qs = Employee.objects.filter(
            Q(pk__in=base_qs.values_list('pk', flat=True))
            | Q(pk__in=extra.values_list('pk', flat=True)),
        ).distinct()

    if exclude_ids:
        base_qs = base_qs.exclude(id__in=exclude_ids)

    return base_qs


def transfer_breakdown_for_employee(evt: TransferEvent | None) -> dict:
    if not evt:
        return {}
    return {
        'transfer_date': evt.transfer_date.isoformat(),
        'from_branch_id': evt.from_branch_id,
        'from_branch_name': evt.from_branch_name,
        'to_branch_id': evt.to_branch_id,
        'to_branch_name': evt.to_branch_name,
        'salary_branch_id': evt.to_branch_id,
        'rule': 'full_salary_new_branch',
        'note': 'الراتب كامل على الفرع الجديد عند النقل في الشهر',
    }


def _standard_line_net(
    employee: Employee,
    company_id: int,
    year: int,
    month: int,
    salary_mode: str,
    sponsorship_id: int | None,
) -> Decimal | None:
    """صافي من مسير عادي موجود على فرع الموظف الحالي."""
    line = (
        PayrollLine.objects.filter(
            employee_id=employee.id,
            run__run_kind=PayrollRun.RunKind.STANDARD,
            run__period_year=year,
            run__period_month=month,
            run__salary_mode=salary_mode,
            run__branch_id=employee.branch_id,
        )
        .order_by('-run__updated_at')
        .first()
    )
    if line:
        return line.net_salary
    if salary_mode == PayrollRun.SalaryMode.TRANSFER and sponsorship_id:
        if line := PayrollLine.objects.filter(
            employee_id=employee.id,
            run__run_kind=PayrollRun.RunKind.STANDARD,
            run__period_year=year,
            run__period_month=month,
            run__salary_mode=salary_mode,
            run__sponsorship_id=sponsorship_id,
            run__branch__company_id=company_id,
        ).first():
            return line.net_salary
    return None


@transaction.atomic
def build_payroll_detailed_run(
    company,
    year: int,
    month: int,
    user=None,
    *,
    salary_mode: str,
    sponsorship_id: int | None = None,
    sponsorship_scope_ids: list[int] | None = None,
) -> PayrollRun:
    """مسير تفصيلي موحّد على مستوى الشركة — توزيع تحمّل الفروع للمنقولين."""
    if salary_mode == PayrollRun.SalaryMode.CASH:
        scope_ids = None
    else:
        if sponsorship_scope_ids is not None:
            scope_ids = list(sponsorship_scope_ids)
        elif sponsorship_id:
            scope_ids = [sponsorship_id]
        else:
            scope_ids = None
        if scope_ids is not None and not scope_ids:
            raise ValueError('لا توجد شركات كفالة ضمن نطاق المسير التفصيلي.')

    run, _ = PayrollRun.objects.get_or_create(
        company=company,
        branch=None,
        period_year=year,
        period_month=month,
        salary_mode=salary_mode,
        run_kind=PayrollRun.RunKind.DETAILED,
        sponsorship_id=None,
        defaults={
            'created_by': user,
            'status': PayrollRun.Status.DRAFT,
        },
    )
    if run.status == PayrollRun.Status.LOCKED:
        raise ValueError('المسير التفصيلي مُغلق ولا يمكن إعادة بنائه.')

    PayrollRun.acquire_row_lock(run.pk)
    _purge_other_detailed_draft_runs(
        company_id=company.id,
        year=year,
        month=month,
        salary_mode=salary_mode,
        keep_pk=run.pk,
    )
    PayrollAllocationLine.all_objects.filter(run=run).delete()

    transfers = transfers_in_period(company.id, year, month)
    period_start, period_end = calendar_period_bounds(year, month)
    alloc_rows: list[PayrollAllocationLine] = []

    for emp_id, evt in transfers.items():
        emp = Employee.objects.filter(pk=emp_id).select_related('branch').first()
        if not emp or not _employee_matches_salary_mode(emp, salary_mode, scope_ids):
            continue

        lookup_sponsorship_id = (
            emp.sponsorship_id
            if salary_mode == PayrollRun.SalaryMode.TRANSFER
            else None
        )
        net = _standard_line_net(
            emp, company.id, year, month, salary_mode, lookup_sponsorship_id,
        )
        if net is None:
            from apps.payroll.services.engine import _compute_employee_payroll_snapshot

            snap_sponsorship_id = (
                scope_ids[0] if scope_ids and len(scope_ids) == 1 else emp.sponsorship_id
            )
            snap_run = PayrollRun.objects.filter(
                branch_id=evt.to_branch_id or emp.branch_id,
                period_year=year,
                period_month=month,
                salary_mode=salary_mode,
                run_kind=PayrollRun.RunKind.STANDARD,
            ).first()
            if not snap_run and evt.to_branch_id:
                br = Branch.objects.filter(pk=evt.to_branch_id).first()
                if br:
                    snap_run, _ = PayrollRun.objects.get_or_create(
                        branch=br,
                        period_year=year,
                        period_month=month,
                        salary_mode=salary_mode,
                        run_kind=PayrollRun.RunKind.STANDARD,
                        defaults={
                            'company': company,
                            'sponsorship_id': snap_sponsorship_id,
                            'status': PayrollRun.Status.DRAFT,
                        },
                    )
            if snap_run:
                snap = _compute_employee_payroll_snapshot(emp, year, month, run=snap_run)
                net = snap['net_salary']
            else:
                net = Decimal('0')

        days_old = _days_before_transfer(period_start, evt.transfer_date)
        days_new = _days_after_transfer(period_end, evt.transfer_date)
        note = 'راتب كامل — الفرع الجديد'

        if evt.from_branch_id:
            alloc_rows.append(
                PayrollAllocationLine(
                    run=run,
                    employee_id=emp_id,
                    branch_id=evt.from_branch_id,
                    from_branch_id=evt.from_branch_id,
                    transfer_date=evt.transfer_date,
                    days_in_branch=days_old,
                    net_amount=Decimal('0'),
                    employee_net_total=net,
                    bears_salary=False,
                    transfer_statement_id=evt.statement_id,
                    notes='لا يتحمل راتب الشهر (نقل)',
                )
            )
        if evt.to_branch_id:
            alloc_rows.append(
                PayrollAllocationLine(
                    run=run,
                    employee_id=emp_id,
                    branch_id=evt.to_branch_id,
                    from_branch_id=evt.from_branch_id,
                    transfer_date=evt.transfer_date,
                    days_in_branch=days_new,
                    net_amount=net,
                    employee_net_total=net,
                    bears_salary=True,
                    transfer_statement_id=evt.statement_id,
                    notes=note,
                )
            )

    if alloc_rows:
        PayrollAllocationLine.objects.bulk_create(alloc_rows, batch_size=500)

    run.recompute_detailed_totals()
    return run


def build_detailed_runs_for_branches(
    branches,
    year: int,
    month: int,
    user,
    *,
    salary_mode: str,
    sponsorship_scope_ids: list[int] | None = None,
) -> list[PayrollRun]:
    """مسودة تفصيلية موحّدة واحدة لكل شركة ضمن الفروع المحددة."""
    companies = {}
    for br in branches:
        if br.company_id:
            companies[br.company_id] = br.company

    built = []
    for company in companies.values():
        built.append(
            build_payroll_detailed_run(
                company, year, month, user,
                salary_mode=salary_mode,
                sponsorship_scope_ids=(
                    sponsorship_scope_ids
                    if salary_mode == PayrollRun.SalaryMode.TRANSFER
                    else None
                ),
            )
        )
    return built
