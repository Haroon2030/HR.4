"""قواعد قفل تعديل/حذف سجلات ملف الموظف."""
from __future__ import annotations

from django.db.models import Q

from apps.employees.models import EmployeeLedger, EmployeeLeave, EmployeeLoan, EmployeeStatement, LoanInstallment

EDITABLE_STATEMENT_TYPES = frozenset({
    EmployeeStatement.StatementType.STATEMENT,
    EmployeeStatement.StatementType.WARNING,
    EmployeeStatement.StatementType.FINAL_WARNING,
    EmployeeStatement.StatementType.PENALTY,
    EmployeeStatement.StatementType.ACKNOWLEDGMENT,
    EmployeeStatement.StatementType.OTHER,
})


def statement_is_editable(statement: EmployeeStatement) -> bool:
    if statement.statement_type not in EDITABLE_STATEMENT_TYPES:
        return False
    return not statement.applied_to_payroll_id


def loan_has_consumed_installments(loan: EmployeeLoan) -> bool:
    return loan.installments_log.filter(
        Q(status=LoanInstallment.Status.PAID) | Q(applied_to_payroll__isnull=False),
    ).exists()


def loan_is_editable(loan: EmployeeLoan) -> bool:
    return not loan_has_consumed_installments(loan)


def ledger_entry_is_locked(entry: EmployeeLedger) -> bool:
    if entry.payroll_run_id:
        return True
    return entry.transaction_type == EmployeeLedger.TransactionType.FINAL_SETTLEMENT


def leave_is_editable(leave: EmployeeLeave) -> bool:
    return not leave.applied_to_payroll_id
