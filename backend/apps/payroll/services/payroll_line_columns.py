"""تعريف أعمدة تصدير مسير الرواتب (Excel) — تنسيق كشف الرواتب المعتمد."""
from __future__ import annotations

from decimal import Decimal

from apps.core.salary_month import calendar_period_bounds

# (مفتاح الحقل، عنوان العمود، لون الترويسة، النوع: text | money | days)
# الترتيب من اليمين لليسار (عمود 1 = أقصى اليمين في Excel RTL)
PAYROLL_LINE_COLUMNS = [
    ('employee_number', 'الرقم الوظيفي', 'blue', 'text'),
    ('employee_name', 'الاسم', 'blue', 'text'),
    ('account_number', 'رقم الحساب', 'yellow', 'text'),
    ('bank', 'البنك', 'yellow', 'text'),
    ('account_type', 'طبيعة الحساب', 'yellow', 'text'),
    ('salary_gross', 'الراتب', 'yellow', 'money'),
    ('id_number', 'رقم الهوية', 'blue', 'text'),
    ('branch', 'الفرع', 'blue', 'text'),
    ('company', 'الشركة', 'blue', 'text'),
    ('period_start', 'تاريخ البداية', 'blue', 'text'),
    ('period_end', 'تاريخ الإقفال', 'blue', 'text'),
    ('worked_days', 'عدد الأيام', 'blue', 'days'),
    ('basic_salary', 'الراتب الأساسي', 'blue', 'money'),
    ('earned_basic', 'الراتب المستحق', 'cyan', 'money'),
    ('housing_allowance', 'بدل السكن', 'blue', 'money'),
    ('earned_housing', 'بدل سكن المستحق', 'cyan', 'money'),
    ('transport_allowance', 'بدل الانتقال', 'blue', 'money'),
    ('fixed_other_allowance', 'بدل إضافي ثابت', 'blue', 'money'),
    ('additional', 'إضافي', 'blue', 'money'),
    ('total_allowances', 'إجمالي البدلات', 'cyan', 'money'),
    ('total_earnings', 'إجمالي الراتب المستحق', 'blue', 'money'),
    ('penalties_deductions', 'جزاءات و خصومات', 'blue', 'money'),
    ('insurance_deduction', 'خصم تأمينات إجتماعية 9.75', 'blue', 'money'),
    ('loan_deduction', 'راتب مقدم ( سلف )', 'blue', 'money'),
    ('total_deductions', 'إجمالي الخصومات', 'cyan', 'money'),
    ('net_salary', 'الصافي', 'blue', 'money'),
    ('payment', 'الدفع', 'blue', 'text'),
]

HEADER_FILL_COLORS = {
    'yellow': 'FFFF99',
    'cyan': '00FFFF',
    'blue': 'B4C6E7',
}

MONEY_SUM_KEYS = {
    key for key, _label, _color, col_type in PAYROLL_LINE_COLUMNS if col_type == 'money'
}


def payroll_lines_select_related(qs):
    return qs.select_related(
        'employee',
        'employee__branch',
        'employee__branch__company',
        'employee__bank',
        'employee__sponsorship',
    )


def _q(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal('0.01'))


def _worked_days(line) -> Decimal:
    month_days = Decimal(line.month_days or 30)
    absent = Decimal(line.absence_days or 0) + Decimal(line.unpaid_leave_days or 0)
    worked = month_days - absent
    if worked < 0:
        worked = Decimal('0')
    return worked


def _prorate(line, amount) -> Decimal:
    month_days = Decimal(line.month_days or 30)
    if month_days <= 0:
        return Decimal('0')
    return _q(Decimal(amount or 0) * _worked_days(line) / month_days)


def _company_name(line, run) -> str:
    if run.company_id:
        return run.company.name or ''
    emp = line.employee
    if emp.branch_id and getattr(emp.branch, 'company_id', None):
        return emp.branch.company.name or ''
    if emp.sponsorship_id:
        return (emp.sponsorship.company_name or '').strip()
    return ''


def resolve_cell_value(line, run, key: str):
    emp = line.employee
    if key == 'employee_number':
        return emp.employee_number or ''
    if key == 'employee_name':
        return emp.name or ''
    if key == 'account_number':
        return (emp.iban or '').strip()
    if key == 'bank':
        return emp.bank.name if emp.bank_id else ''
    if key == 'account_type':
        from apps.employees.services.salary_payment import account_type_export_label
        return account_type_export_label(emp)
    if key == 'salary_gross':
        return line.gross_salary
    if key == 'id_number':
        return emp.id_number or ''
    if key == 'branch':
        if emp.branch_id:
            return emp.branch.name
        return run.branch.name if run.branch_id else ''
    if key == 'company':
        return _company_name(line, run)
    if key == 'period_start':
        start, _end = calendar_period_bounds(run.period_year, run.period_month)
        return start.isoformat()
    if key == 'period_end':
        _start, end = calendar_period_bounds(run.period_year, run.period_month)
        return end.isoformat()
    if key == 'worked_days':
        return _worked_days(line)
    if key == 'basic_salary':
        return line.basic_salary
    if key == 'earned_basic':
        return _prorate(line, line.basic_salary)
    if key == 'housing_allowance':
        return line.housing_allowance
    if key == 'earned_housing':
        return _prorate(line, line.housing_allowance)
    if key == 'transport_allowance':
        return line.transport_allowance
    if key == 'fixed_other_allowance':
        return line.other_allowance
    if key == 'additional':
        return _q(line.bonus) + _q(line.overtime) + _q(line.other_addition)
    if key == 'total_allowances':
        return (
            _q(line.housing_allowance)
            + _q(line.transport_allowance)
            + _q(line.other_allowance)
            + _q(line.meal_allowance)
            + _q(line.cash_amount)
        )
    if key == 'total_earnings':
        return line.total_earnings
    if key == 'penalties_deductions':
        return (
            _q(line.absence_deduction)
            + _q(line.unpaid_leave_deduction)
            + _q(line.penalty_deduction)
            + _q(line.other_deduction)
        )
    if key == 'insurance_deduction':
        return line.insurance_deduction
    if key == 'loan_deduction':
        return line.loan_deduction
    if key == 'total_deductions':
        return line.total_deductions
    if key == 'net_salary':
        return line.net_salary
    if key == 'payment':
        return run.get_salary_mode_display()
    return ''
