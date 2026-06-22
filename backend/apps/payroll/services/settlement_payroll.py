"""إزالة الموظف من مسيرات الرواتب المسودة عند التصفية."""
from __future__ import annotations

from apps.employees.models import Employee


def remove_employee_from_draft_payroll_runs(employee: Employee | int) -> dict[str, int]:
    """
    يحذف سطور الموظف من كل مسير DRAFT (عادي وتفصيلي).
    يُستدعى تلقائياً عند التصفية/إنهاء الخدمة.
    """
    from apps.payroll.models import PayrollAllocationLine, PayrollLine, PayrollRun

    employee_id = employee.pk if isinstance(employee, Employee) else employee

    lines = PayrollLine.all_objects.filter(
        employee_id=employee_id,
        run__status=PayrollRun.Status.DRAFT,
    )
    lines_removed = lines.count()
    if lines_removed:
        lines.hard_delete()

    allocs = PayrollAllocationLine.all_objects.filter(
        employee_id=employee_id,
        run__status=PayrollRun.Status.DRAFT,
    )
    detailed_run_ids = list(
        allocs.filter(run__run_kind=PayrollRun.RunKind.DETAILED)
        .values_list('run_id', flat=True)
        .distinct(),
    )
    allocations_removed = allocs.count()
    if allocations_removed:
        allocs.hard_delete()

    if detailed_run_ids:
        for run in PayrollRun.objects.filter(pk__in=detailed_run_ids):
            run.recompute_detailed_totals()

    return {
        'lines_removed': lines_removed,
        'allocations_removed': allocations_removed,
    }
