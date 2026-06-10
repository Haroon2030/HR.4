"""تعريف أعمدة تصدير مسير الرواتب (Excel) — تنسيق كشف الرواتب المعتمد."""
from __future__ import annotations

from decimal import Decimal

from apps.payroll.models import PayrollRun
from apps.payroll.services.period_eligibility import period_from_line_breakdown, prorate_amount

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


def _payable_worked_days(line, run) -> Decimal:
    period = period_from_line_breakdown(line, run)
    base = period['payable_base_days']
    absent = Decimal(line.absence_days or 0) + Decimal(line.unpaid_leave_days or 0)
    worked = base - absent
    if worked < 0:
        worked = Decimal('0')
    return worked


def _worked_days(line, run) -> Decimal:
    return _payable_worked_days(line, run)


def _prorate(line, run, amount) -> Decimal:
    period = period_from_line_breakdown(line, run)
    return prorate_amount(amount, _payable_worked_days(line, run), period['month_days'])


def _company_name(line, run) -> str:
    """عمود الشركة في التصدير: شركة الكفالة لمسير التحويل، وإلا المنشأة."""
    emp = line.employee
    if run.salary_mode == PayrollRun.SalaryMode.TRANSFER:
        sponsorship = getattr(run, 'sponsorship', None)
        if sponsorship:
            return (sponsorship.company_name or '').strip()
        if emp.sponsorship_id and getattr(emp, 'sponsorship', None):
            return (emp.sponsorship.company_name or '').strip()
    if run.company_id:
        return run.company.name or ''
    if emp.branch_id and getattr(emp.branch, 'company_id', None):
        return emp.branch.company.name or ''
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
        return period_from_line_breakdown(line, run)['period_start'].isoformat()
    if key == 'period_end':
        return period_from_line_breakdown(line, run)['period_end'].isoformat()
    if key == 'worked_days':
        return _worked_days(line, run)
    if key == 'basic_salary':
        return line.basic_salary
    if key == 'earned_basic':
        return _prorate(line, run, line.basic_salary)
    if key == 'housing_allowance':
        return line.housing_allowance
    if key == 'earned_housing':
        return _prorate(line, run, line.housing_allowance)
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


def _column_type(key: str) -> str:
    for col_key, _label, _color, col_type in PAYROLL_LINE_COLUMNS:
        if col_key == key:
            return col_type
    return 'text'


def lookup_source_payroll_line(alloc_line, run: PayrollRun):
    """سطر مسير عادي/موحّد لنفس الموظف والفترة — مصدر بيانات الراتب للتصدير التفصيلي."""
    from apps.payroll.models import PayrollLine

    qs = PayrollLine.objects.filter(
        employee_id=alloc_line.employee_id,
        run__period_year=run.period_year,
        run__period_month=run.period_month,
        run__salary_mode=run.salary_mode,
        run__run_kind__in=(
            PayrollRun.RunKind.STANDARD,
            PayrollRun.RunKind.CONSOLIDATED,
        ),
    )
    emp = alloc_line.employee
    if run.salary_mode == PayrollRun.SalaryMode.TRANSFER and emp.sponsorship_id:
        qs = qs.filter(run__sponsorship_id=emp.sponsorship_id)
    return payroll_lines_select_related(qs).order_by('-run__pk').first()


def build_ephemeral_payroll_line(emp, run: PayrollRun):
    """سطر مسير غير محفوظ من snapshot — عند غياب مسير عادي للموظف."""
    from apps.payroll.models import PayrollLine
    from apps.payroll.services.engine import _compute_employee_payroll_snapshot

    snap = _compute_employee_payroll_snapshot(
        emp, run.period_year, run.period_month, run=run,
    )
    return PayrollLine(
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
        breakdown=snap.get('breakdown', {}),
    )


def resolve_detailed_allocation_cell_value(alloc_line, run: PayrollRun, key: str, payroll_line):
    """
    أعمدة كشف الرواتب مع بيانات المسير التفصيلي:
    الفرع وأيام التواجد من سطر التوزيع؛ المبالغ كاملة للفرع المتحمّل وصفر للفرع السابق.
    """
    if key == 'branch':
        return alloc_line.branch.name
    if key == 'worked_days':
        return alloc_line.days_in_branch
    if not alloc_line.bears_salary and _column_type(key) == 'money':
        return Decimal('0')
    return resolve_cell_value(payroll_line, run, key)
