"""
التقارير — بيانات تفصيلية بصفوف وأعمدة
كل تقرير يُرجع: columns (أعمدة) + rows (صفوف) + title
"""
from datetime import date, timedelta
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.db.models import Count, Sum, Q, F
from django.db.models.functions import Coalesce

from apps.core.decorators import permission_required

REPORT_GROUPS = [
    {'key': 'workforce',    'title': 'القوى العاملة',    'icon': 'users-round',   'color': 'primary',  'description': 'توزيع الموظفين على الفروع والأقسام'},
    {'key': 'salary',       'title': 'الرواتب والمصاريف', 'icon': 'wallet',        'color': 'emerald',  'description': 'تحليل الرواتب والبدلات والاستقطاعات'},
    {'key': 'turnover',     'title': 'الدوران الوظيفي',   'icon': 'refresh-cw',    'color': 'indigo',   'description': 'التعيينات والإنهاءات ومعدل الدوران'},
    {'key': 'compliance',   'title': 'الالتزام والوثائق', 'icon': 'shield-check',  'color': 'rose',     'description': 'الوثائق والكروت الصحية والإنذارات'},
    {'key': 'leaves',       'title': 'الإجازات والغياب',  'icon': 'calendar-days', 'color': 'cyan',     'description': 'تقارير الإجازات والغياب'},
    {'key': 'demographics', 'title': 'تقارير ديموغرافية', 'icon': 'pie-chart',     'color': 'amber',    'description': 'توزيع حسب الجنس والجنسية والمهنة'},
]

REPORTS = [
    {'group': 'workforce', 'key': 'headcount_summary',     'title': 'ملخص القوى العاملة',          'icon': 'users-round',   'color': 'primary',  'description': 'إجمالي الموظفين حسب الحالة والفرع'},
    {'group': 'workforce', 'key': 'branches',              'title': 'الموظفون حسب الفروع',         'icon': 'building-2',    'color': 'primary',  'description': 'توزيع الموظفين على الفروع'},
    {'group': 'workforce', 'key': 'departments_overview',  'title': 'الموظفون حسب الأقسام',        'icon': 'network',       'color': 'primary',  'description': 'توزيع الموظفين على الأقسام'},
    {'group': 'workforce', 'key': 'cost_centers_overview', 'title': 'الموظفون حسب مراكز التكلفة',  'icon': 'layers',        'color': 'primary',  'description': 'توزيع الموظفين والتكلفة'},
    {'group': 'salary',    'key': 'salary_expenses',       'title': 'تفاصيل الرواتب',              'icon': 'wallet',        'color': 'emerald',  'description': 'رواتب كل موظف بالتفصيل'},
    {'group': 'salary',    'key': 'allowances_breakdown',  'title': 'تفصيل البدلات',               'icon': 'plus-circle',   'color': 'emerald',  'description': 'بدلات كل موظف'},
    {'group': 'salary',    'key': 'deductions_breakdown',  'title': 'تفصيل الاستقطاعات',           'icon': 'minus-circle',  'color': 'emerald',  'description': 'استقطاعات آخر مسير'},
    {'group': 'salary',    'key': 'insurance_costs',       'title': 'بيانات التأمين',              'icon': 'shield',        'color': 'emerald',  'description': 'تأمين كل موظف'},
    {'group': 'turnover',  'key': 'new_hires',             'title': 'التعيينات الجديدة',           'icon': 'user-plus',     'color': 'indigo',   'description': 'الموظفون المعينون حديثاً'},
    {'group': 'turnover',  'key': 'terminations',          'title': 'انتهاء العقود',               'icon': 'user-minus',    'color': 'indigo',   'description': 'الموظفون المنتهية عقودهم والمصفون'},
    {'group': 'turnover',  'key': 'tenure_analysis',       'title': 'تحليل فترة الخدمة',           'icon': 'hourglass',     'color': 'indigo',   'description': 'مدة خدمة كل موظف'},
    {'group': 'compliance','key': 'passport_expiry',       'title': 'انتهاء الجوازات',             'icon': 'book-open',     'color': 'rose',     'description': 'الجوازات المنتهية أو القاربة'},
    {'group': 'compliance','key': 'health_cards',          'title': 'الكروت الصحية',               'icon': 'heart-pulse',   'color': 'rose',     'description': 'حالة الكروت الصحية'},
    {'group': 'compliance','key': 'warnings',              'title': 'الإنذارات والمخالفات',        'icon': 'alert-triangle','color': 'rose',     'description': 'الإنذارات والمخالفات'},
    {'group': 'leaves',    'key': 'leaves',                'title': 'سجل الإجازات',                'icon': 'plane',         'color': 'cyan',     'description': 'كل الإجازات المسجلة'},
    {'group': 'leaves',    'key': 'leave_balance',         'title': 'رصيد الإجازات',               'icon': 'calendar-clock','color': 'cyan',     'description': 'رصيد كل موظف'},
    {'group': 'leaves',    'key': 'absences',              'title': 'سجل الغياب',                  'icon': 'user-x',        'color': 'cyan',     'description': 'كل سجلات الغياب'},
    {'group': 'demographics','key': 'gender',              'title': 'حسب الجنس',                   'icon': 'users',         'color': 'amber',    'description': 'توزيع الموظفين حسب الجنس'},
    {'group': 'demographics','key': 'nationality',         'title': 'حسب الجنسية',                 'icon': 'flag',          'color': 'amber',    'description': 'توزيع حسب الجنسية'},
    {'group': 'demographics','key': 'professions',         'title': 'حسب المهنة',                  'icon': 'briefcase',     'color': 'amber',    'description': 'توزيع حسب المهنة'},
]

def _grouped_reports():
    return [{**g, 'items': [r for r in REPORTS if r['group'] == g['key']]} for g in REPORT_GROUPS]

def _emp_qs():
    from apps.employees.models import Employee
    return Employee.objects.filter(is_deleted=False)

def _active():
    from apps.employees.models import Employee
    return _emp_qs().filter(status__in=[Employee.Status.ACTIVE, Employee.Status.LEAVE])

# ══════════════════════════════════════════════════════════════════════════════
# دوال البناء — كل واحدة تُرجع columns + rows
# ══════════════════════════════════════════════════════════════════════════════

def _build_headcount_summary(req):
    from apps.employees.models import Employee
    cols = ['الاسم', 'الرقم الوظيفي', 'الفرع', 'القسم', 'الحالة', 'تاريخ المباشرة']
    labels = dict(Employee.Status.choices)
    qs = _emp_qs().select_related('branch', 'department').order_by('branch__name', 'name')
    rows = [[e.name, e.employee_number or '—', e.branch.name if e.branch else '—', e.department.name if e.department else '—', labels.get(e.status, e.status), str(e.hire_date or '—')] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_branches(req):
    cols = ['الاسم', 'الرقم الوظيفي', 'الفرع', 'الأساسي', 'سكن', 'نقل', 'إضافي', 'كاش', 'الإجمالي']
    qs = _active().select_related('branch').order_by('branch__name', 'name')
    rows = [[e.name, e.employee_number or '—', e.branch.name if e.branch else '—', str(e.basic_salary), str(e.housing_allowance), str(e.transport_allowance), str(e.other_allowance), str(e.cash_amount), str(e.total_salary)] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_departments_overview(req):
    cols = ['الاسم', 'الفرع', 'القسم', 'مركز التكلفة', 'المسمى الوظيفي']
    qs = _active().select_related('branch', 'department', 'cost_center', 'profession').order_by('branch__name', 'department__name', 'name')
    rows = [[e.name, e.branch.name if e.branch else '—', e.department.name if e.department else '—', e.cost_center.name if e.cost_center else '—', e.profession.name if e.profession else '—'] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_cost_centers_overview(req):
    cols = ['الاسم', 'مركز التكلفة', 'الفرع', 'القسم', 'الإجمالي']
    qs = _active().select_related('branch', 'department', 'cost_center').order_by('cost_center__name', 'name')
    rows = [[e.name, e.cost_center.name if e.cost_center else '—', e.branch.name if e.branch else '—', e.department.name if e.department else '—', str(e.total_salary)] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_salary_expenses(req):
    cols = ['الاسم', 'الفرع', 'الأساسي', 'سكن', 'نقل', 'إضافي', 'كاش', 'الإجمالي']
    qs = _active().select_related('branch').order_by('branch__name', 'name')
    rows = [[e.name, e.branch.name if e.branch else '—', str(e.basic_salary), str(e.housing_allowance), str(e.transport_allowance), str(e.other_allowance), str(e.cash_amount), str(e.total_salary)] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_allowances_breakdown(req):
    cols = ['الاسم', 'الفرع', 'سكن', 'نقل', 'إضافي', 'كاش', 'إجمالي البدلات']
    qs = _active().select_related('branch').order_by('branch__name', 'name')
    rows = []
    for e in qs:
        t = e.housing_allowance + e.transport_allowance + e.other_allowance + e.cash_amount
        rows.append([e.name, e.branch.name if e.branch else '—', str(e.housing_allowance), str(e.transport_allowance), str(e.other_allowance), str(e.cash_amount), str(t)])
    return {'columns': cols, 'rows': rows}

def _build_deductions_breakdown(req):
    from apps.payroll.models import PayrollRun
    last = PayrollRun.objects.filter(status=PayrollRun.Status.LOCKED).order_by('-period_year', '-period_month').first()
    cols = ['الموظف', 'غياب', 'إجازة بدون راتب', 'سلف', 'مخالفات', 'تأمينات', 'أخرى', 'إجمالي الخصم']
    if not last:
        return {'columns': cols, 'rows': [], 'note': 'لا يوجد مسير مُرحَّل'}
    lines = last.lines.select_related('employee').order_by('employee__name')
    rows = [[l.employee.name, str(l.absence_deduction), str(l.unpaid_leave_deduction), str(l.loan_deduction), str(l.penalty_deduction), str(l.insurance_deduction), str(l.other_deduction), str(l.total_deductions)] for l in lines]
    return {'columns': cols, 'rows': rows, 'note': f'من مسير: {last}'}

def _build_insurance_costs(req):
    cols = ['الاسم', 'الفرع', 'شركة التأمين', 'فئة التأمين', 'نسبة الخصم %']
    qs = _active().select_related('branch', 'insurance', 'insurance_class').order_by('insurance__name', 'name')
    rows = [[e.name, e.branch.name if e.branch else '—', e.insurance.name if e.insurance else '—', e.insurance_class.name if e.insurance_class else '—', str(e.insurance_deduction_rate)] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_new_hires(req):
    from apps.employees.models import Employee
    start = date.today() - timedelta(days=180)
    cols = ['الاسم', 'الرقم الوظيفي', 'الفرع', 'القسم', 'تاريخ المباشرة', 'الجنسية']
    qs = _emp_qs().filter(hire_date__gte=start).exclude(status=Employee.Status.TERMINATED).select_related('branch', 'department', 'nationality').order_by('-hire_date')
    rows = [[e.name, e.employee_number or '—', e.branch.name if e.branch else '—', e.department.name if e.department else '—', str(e.hire_date or '—'), e.nationality.name if e.nationality else '—'] for e in qs]
    return {'columns': cols, 'rows': rows, 'note': 'آخر 6 أشهر'}

def _build_terminations(req):
    from apps.employees.models import Employee
    cols = ['الاسم', 'الفرع', 'تاريخ المباشرة', 'تاريخ الانتهاء', 'السبب', 'إجمالي الراتب الأخير']
    qs = _emp_qs().filter(status=Employee.Status.TERMINATED).select_related('branch').order_by('-end_date')
    rows = [[e.name, e.branch.name if e.branch else '—', str(e.hire_date or '—'), str(e.end_date or '—'), e.end_reason or '—', str(e.total_salary)] for e in qs]
    return {'columns': cols, 'rows': rows, 'note': 'قائمة بكل الموظفين المنتهية عقودهم والمُصفَّين'}

def _build_tenure_analysis(req):
    today = date.today()
    cols = ['الاسم', 'الفرع', 'تاريخ المباشرة', 'مدة الخدمة (سنة)', 'مدة الخدمة (يوم)']
    qs = _active().exclude(hire_date__isnull=True).select_related('branch').order_by('hire_date')
    rows = []
    for e in qs:
        days = (today - e.hire_date).days
        years = round(days / 365.25, 1)
        rows.append([e.name, e.branch.name if e.branch else '—', str(e.hire_date), str(years), str(days)])
    return {'columns': cols, 'rows': rows}

def _build_passport_expiry(req):
    today = date.today()
    soon = today + timedelta(days=90)
    cols = ['الاسم', 'الفرع', 'تاريخ انتهاء الجواز', 'الحالة']
    qs = _active().exclude(passport_expiry_date__isnull=True).select_related('branch').order_by('passport_expiry_date')
    rows = []
    for e in qs:
        if e.passport_expiry_date < today:
            status = '❌ منتهي'
        elif e.passport_expiry_date <= soon:
            status = '⚠️ ينتهي قريباً'
        else:
            status = '✅ ساري'
        rows.append([e.name, e.branch.name if e.branch else '—', str(e.passport_expiry_date), status])
    return {'columns': cols, 'rows': rows}

def _build_health_cards(req):
    today = date.today()
    soon = today + timedelta(days=90)
    cols = ['الاسم', 'الفرع', 'حالة الكرت', 'تاريخ الانتهاء', 'الوضع']
    qs = _active().select_related('branch').order_by('branch__name', 'name')
    labels = {'available': 'متوفر', 'not_available': 'غير متوفر'}
    rows = []
    for e in qs:
        st = labels.get(e.health_card_status, e.health_card_status)
        exp = str(e.health_card_expiry) if e.health_card_expiry else '—'
        if not e.health_card_expiry:
            flag = '—'
        elif e.health_card_expiry < today:
            flag = '❌ منتهي'
        elif e.health_card_expiry <= soon:
            flag = '⚠️ ينتهي قريباً'
        else:
            flag = '✅ ساري'
        rows.append([e.name, e.branch.name if e.branch else '—', st, exp, flag])
    return {'columns': cols, 'rows': rows}

def _build_warnings(req):
    from apps.employees.models import EmployeeStatement
    cols = ['الموظف', 'الفرع', 'النوع', 'العنوان', 'التاريخ', 'مبلغ الخصم']
    types = [EmployeeStatement.StatementType.WARNING, EmployeeStatement.StatementType.FINAL_WARNING, EmployeeStatement.StatementType.PENALTY]
    qs = EmployeeStatement.objects.filter(statement_type__in=types, is_deleted=False).select_related('employee', 'employee__branch').order_by('-statement_date')[:200]
    labels = dict(EmployeeStatement.StatementType.choices)
    rows = [[s.employee.name, s.employee.branch.name if s.employee.branch else '—', labels.get(s.statement_type, s.statement_type), s.title, str(s.statement_date), str(s.deduction_amount)] for s in qs]
    return {'columns': cols, 'rows': rows}

def _build_leaves(req):
    from apps.employees.models import EmployeeLeave
    cols = ['الموظف', 'الفرع', 'نوع الإجازة', 'من', 'إلى', 'عدد الأيام']
    labels = dict(EmployeeLeave.LeaveType.choices)
    qs = EmployeeLeave.objects.filter(is_deleted=False).select_related('employee', 'employee__branch').order_by('-date_from')[:300]
    rows = [[l.employee.name, l.employee.branch.name if l.employee.branch else '—', labels.get(l.leave_type, l.leave_type), str(l.date_from), str(l.date_to), str(l.days)] for l in qs]
    return {'columns': cols, 'rows': rows}

def _build_leave_balance(req):
    cols = ['الاسم', 'الفرع', 'تاريخ المباشرة', 'المستحق', 'المستخدم', 'المتبقي']
    qs = _active().exclude(hire_date__isnull=True).exclude(sponsorship__isnull=True).select_related('branch').order_by('branch__name', 'name')
    rows = [[e.name, e.branch.name if e.branch else '—', str(e.hire_date), str(e.accrued_leave_days), str(e.available_leave_balance), str(e.remaining_leave_days)] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_absences(req):
    from apps.employees.models import EmployeeAbsence
    cols = ['الموظف', 'الفرع', 'تاريخ الغياب', 'عدد الأيام', 'مبلغ الخصم', 'محتسب في مسير']
    qs = EmployeeAbsence.objects.filter(is_deleted=False).select_related('employee', 'employee__branch', 'applied_to_payroll').order_by('-absence_date')[:300]
    rows = [[a.employee.name, a.employee.branch.name if a.employee.branch else '—', str(a.absence_date), str(a.days), str(a.deduction_amount), str(a.applied_to_payroll or '—')] for a in qs]
    return {'columns': cols, 'rows': rows}

def _build_gender(req):
    from apps.employees.models import Employee
    cols = ['الاسم', 'الفرع', 'الجنس', 'الجنسية', 'المهنة']
    labels = dict(Employee.Gender.choices)
    qs = _active().select_related('branch', 'nationality', 'profession').order_by('gender', 'name')
    rows = [[e.name, e.branch.name if e.branch else '—', labels.get(e.gender, e.gender or 'غير محدد'), e.nationality.name if e.nationality else '—', e.profession.name if e.profession else '—'] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_nationality(req):
    cols = ['الاسم', 'الفرع', 'الجنسية', 'رقم الهوية', 'رقم الجوال']
    qs = _active().select_related('branch', 'nationality').order_by('nationality__name', 'name')
    rows = [[e.name, e.branch.name if e.branch else '—', e.nationality.name if e.nationality else '—', e.id_number or '—', e.phone or '—'] for e in qs]
    return {'columns': cols, 'rows': rows}

def _build_professions(req):
    cols = ['الاسم', 'الفرع', 'المهنة', 'الجنسية', 'الراتب الإجمالي']
    qs = _active().select_related('branch', 'profession', 'nationality').order_by('profession__name', 'name')
    rows = [[e.name, e.branch.name if e.branch else '—', e.profession.name if e.profession else '—', e.nationality.name if e.nationality else '—', str(e.total_salary)] for e in qs]
    return {'columns': cols, 'rows': rows}

BUILDERS = {
    'headcount_summary': _build_headcount_summary, 'branches': _build_branches,
    'departments_overview': _build_departments_overview, 'cost_centers_overview': _build_cost_centers_overview,
    'salary_expenses': _build_salary_expenses, 'allowances_breakdown': _build_allowances_breakdown,
    'deductions_breakdown': _build_deductions_breakdown, 'insurance_costs': _build_insurance_costs,
    'new_hires': _build_new_hires, 'terminations': _build_terminations, 'tenure_analysis': _build_tenure_analysis,
    'passport_expiry': _build_passport_expiry, 'health_cards': _build_health_cards, 'warnings': _build_warnings,
    'leaves': _build_leaves, 'leave_balance': _build_leave_balance, 'absences': _build_absences,
    'gender': _build_gender, 'nationality': _build_nationality, 'professions': _build_professions,
}

@login_required
@permission_required('reports.view')
def reports_index(request):
    return render(request, 'pages/reports/index.html', {'report_groups': _grouped_reports(), 'reports': REPORTS})

@login_required
@permission_required('reports.view')
def multi_report_detail(request):
    report_keys = request.GET.get('reports', '').split(',')
    selected_reports = []
    
    for key in report_keys:
        key = key.strip()
        if not key:
            continue
        meta = next((r for r in REPORTS if r['key'] == key), None)
        if meta:
            builder = BUILDERS.get(key)
            data = builder(request) if builder else {'columns': [], 'rows': []}
            selected_reports.append({
                'meta': meta,
                'data': data
            })
            
    if not selected_reports:
        raise Http404("لا توجد تقارير محددة لعرضها")
        
    return render(request, 'pages/reports/multi_detail.html', {
        'reports_data': selected_reports,
        'reports_count': len(selected_reports)
    })

@login_required
@permission_required('reports.view')
def report_detail(request, report_type):
    meta = next((r for r in REPORTS if r['key'] == report_type), None)
    if not meta:
        raise Http404("تقرير غير معروف")
    group = next((g for g in REPORT_GROUPS if g['key'] == meta.get('group')), None)
    siblings = [r for r in REPORTS if r.get('group') == meta.get('group') and r['key'] != report_type]
    builder = BUILDERS.get(report_type)
    data = builder(request) if builder else {'columns': [], 'rows': []}
    return render(request, 'pages/reports/detail.html', {
        'report_meta': meta, 'group_meta': group, 'siblings': siblings,
        'reports': REPORTS, 'data': data, 'report_type': report_type,
    })
