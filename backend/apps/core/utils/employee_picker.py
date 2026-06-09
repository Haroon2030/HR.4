"""تسلسل موظف لبحث/اختيار الواجهة — مصدر واحد للحقول."""
from __future__ import annotations

from apps.employees.models import Employee


def employee_picker_dict(emp: Employee) -> dict:
    return {
        'id': emp.id,
        'name': emp.name,
        'number': emp.employee_number or '',
        'id_number': emp.id_number or '',
        'dept': emp.department.name if emp.department_id else '',
        'branch': emp.branch.name if emp.branch_id else '',
    }
