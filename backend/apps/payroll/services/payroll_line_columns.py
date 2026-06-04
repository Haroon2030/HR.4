"""تعريف أعمدة تصدير مسير الرواتب (Excel)."""
from __future__ import annotations

# (مفتاح الحقل، العنوان، المجموعة، النوع: text | money | days)
PAYROLL_LINE_COLUMNS = [
    ('employee_number', 'رقم الموظف', 'info', 'text'),
    ('employee', 'اسم الموظف', 'info', 'text'),
    ('branch', 'الفرع', 'info', 'text'),
    ('department', 'القسم', 'info', 'text'),
    ('nationality', 'الجنسية', 'info', 'text'),
    ('id_number', 'رقم الهوية', 'info', 'text'),
    ('salary_period', 'تاريخ الراتب', 'info', 'text'),
    ('salary_mode', 'نوع الراتب', 'info', 'text'),
    ('bank', 'البنك', 'info', 'text'),
    ('iban', 'الآيبان', 'info', 'text'),
    ('basic_salary', 'الراتب الأساسي', 'earning', 'money'),
    ('insurance_deduction', 'تأمينات', 'deduction', 'money'),
    ('other_deduction', 'خصومات أخرى', 'deduction', 'money'),
    ('total_earnings', 'إجمالي الاستحقاقات', 'total', 'money'),
    ('total_deductions', 'إجمالي الخصومات', 'total', 'money'),
    ('net_salary', 'صافي الراتب', 'total', 'money'),
]

GROUP_HEADER_LABELS = {
    'info': 'بيانات الموظف والبنك',
    'earning': 'الاستحقاقات',
    'deduction': 'الخصومات',
    'total': 'الإجماليات',
}


def payroll_lines_select_related(qs):
    return qs.select_related(
        'employee',
        'employee__branch',
        'employee__department',
        'employee__nationality',
        'employee__bank',
    )


def resolve_cell_value(line, run, key: str):
    emp = line.employee
    if key == 'employee_number':
        return emp.employee_number or ''
    if key == 'employee':
        return emp.name or ''
    if key == 'branch':
        if emp.branch_id:
            return emp.branch.name
        return run.branch.name
    if key == 'department':
        return emp.department.name if emp.department_id else ''
    if key == 'nationality':
        return emp.nationality.name if emp.nationality_id else ''
    if key == 'id_number':
        return emp.id_number or ''
    if key == 'salary_period':
        return run.period_label
    if key == 'salary_mode':
        return run.get_salary_mode_display()
    if key == 'bank':
        return emp.bank.name if emp.bank_id else ''
    if key == 'iban':
        return (emp.iban or '').strip()
    return getattr(line, key)
