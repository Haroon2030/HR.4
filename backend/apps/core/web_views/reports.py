"""
التقارير — منطق بناء البيانات وعرض التقارير
=============================================
كل تقرير له دالة _build_xxx تُرجع dict يحتوي البيانات + العنوان.
"""
from datetime import date, timedelta
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.db.models import Count, Sum, Q, F, Value, CharField
from django.db.models.functions import Coalesce

from apps.core.decorators import permission_required


# ══════════════════════════════════════════════════════════════════════════════
# تعريف المجموعات والتقارير
# ══════════════════════════════════════════════════════════════════════════════

REPORT_GROUPS = [
    {'key': 'workforce',    'title': 'القوى العاملة',         'icon': 'users-round',     'color': 'primary',
     'description': 'نظرة عامة على توزيع الموظفين على الفروع والأقسام ومراكز التكلفة'},
    {'key': 'salary',       'title': 'الرواتب والمصاريف',      'icon': 'wallet',          'color': 'emerald',
     'description': 'تحليل الرواتب والبدلات والاستقطاعات والتأمينات'},
    {'key': 'turnover',     'title': 'الدوران الوظيفي',        'icon': 'refresh-cw',      'color': 'indigo',
     'description': 'متابعة التعيينات الجديدة وإنهاء الخدمات ومعدل الدوران'},
    {'key': 'compliance',   'title': 'الالتزام والوثائق',      'icon': 'shield-check',    'color': 'rose',
     'description': 'متابعة الوثائق الرسمية والكروت الصحية والإنذارات'},
    {'key': 'leaves',       'title': 'الإجازات والغياب',       'icon': 'calendar-days',   'color': 'cyan',
     'description': 'تقارير الرصيد والمستهلك من الإجازات والغياب'},
    {'key': 'demographics', 'title': 'تقارير ديموغرافية',      'icon': 'pie-chart',       'color': 'amber',
     'description': 'توزيع الموظفين حسب الجنس والجنسية والمهنة والسن'},
]

REPORTS = [
    # القوى العاملة
    {'group': 'workforce', 'key': 'headcount_summary',    'title': 'ملخص القوى العاملة',         'description': 'إجمالي الموظفين حسب الحالة',                'icon': 'users-round',  'color': 'primary'},
    {'group': 'workforce', 'key': 'branches',             'title': 'الموظفون حسب الفروع',        'description': 'توزيع وأعداد الموظفين على كل فرع',          'icon': 'building-2',   'color': 'primary'},
    {'group': 'workforce', 'key': 'departments_overview', 'title': 'الموظفون حسب الأقسام',       'description': 'توزيع الموظفين على الأقسام',                'icon': 'network',      'color': 'primary'},
    {'group': 'workforce', 'key': 'cost_centers_overview', 'title': 'الموظفون حسب مراكز التكلفة', 'description': 'توزيع الموظفين والتكلفة',                   'icon': 'layers',       'color': 'primary'},
    # الرواتب
    {'group': 'salary', 'key': 'salary_expenses',      'title': 'إجمالي مصاريف الرواتب', 'description': 'إجمالي الرواتب الشهرية حسب الفرع',      'icon': 'wallet',       'color': 'emerald'},
    {'group': 'salary', 'key': 'allowances_breakdown', 'title': 'تفصيل البدلات',         'description': 'تحليل تفصيلي لجميع أنواع البدلات',       'icon': 'plus-circle',  'color': 'emerald'},
    {'group': 'salary', 'key': 'deductions_breakdown', 'title': 'تفصيل الاستقطاعات',     'description': 'تحليل تفصيلي لجميع الاستقطاعات',         'icon': 'minus-circle', 'color': 'emerald'},
    {'group': 'salary', 'key': 'insurance_costs',      'title': 'مصاريف التأمينات',       'description': 'تكلفة التأمينات على المنشأة',             'icon': 'shield',       'color': 'emerald'},
    # الدوران الوظيفي
    {'group': 'turnover', 'key': 'new_hires',       'title': 'التعيينات الجديدة',      'description': 'الموظفون المعينون حديثاً',               'icon': 'user-plus',    'color': 'indigo'},
    {'group': 'turnover', 'key': 'terminations',    'title': 'إنهاء الخدمات',          'description': 'الموظفون المنتهية خدماتهم',              'icon': 'user-minus',   'color': 'indigo'},
    {'group': 'turnover', 'key': 'turnover_rate',   'title': 'معدل الدوران الوظيفي',   'description': 'مقارنة التعيينات والإنهاءات',             'icon': 'refresh-cw',   'color': 'indigo'},
    {'group': 'turnover', 'key': 'tenure_analysis', 'title': 'تحليل فترة الخدمة',      'description': 'متوسط فترة بقاء الموظفين',               'icon': 'hourglass',    'color': 'indigo'},
    # الالتزام
    {'group': 'compliance', 'key': 'id_expiry',        'title': 'انتهاء الهويات',         'description': 'الهويات المنتهية أو القاربة على الانتهاء', 'icon': 'id-card',      'color': 'rose'},
    {'group': 'compliance', 'key': 'passport_expiry',  'title': 'انتهاء الجوازات',        'description': 'الجوازات القاربة على الانتهاء',            'icon': 'book-open',    'color': 'rose'},
    {'group': 'compliance', 'key': 'health_cards',     'title': 'الكروت الصحية',          'description': 'متابعة الكروت الصحية',                    'icon': 'heart-pulse',  'color': 'rose'},
    {'group': 'compliance', 'key': 'warnings',         'title': 'الإنذارات والمخالفات',   'description': 'الإنذارات والمخالفات الصادرة',             'icon': 'alert-triangle','color': 'rose'},
    # الإجازات
    {'group': 'leaves', 'key': 'leaves',        'title': 'الإجازات الممنوحة', 'description': 'تقرير الإجازات بأنواعها',       'icon': 'plane',         'color': 'cyan'},
    {'group': 'leaves', 'key': 'leave_balance', 'title': 'رصيد الإجازات',     'description': 'الرصيد المتاح لكل موظف',        'icon': 'calendar-clock','color': 'cyan'},
    {'group': 'leaves', 'key': 'absences',      'title': 'تقرير الغياب',      'description': 'إحصائيات الغياب حسب الفرع',     'icon': 'user-x',        'color': 'cyan'},
    # ديموغرافيا
    {'group': 'demographics', 'key': 'gender',           'title': 'حسب الجنس',          'description': 'توزيع الموظفين حسب الجنس',       'icon': 'users',     'color': 'amber'},
    {'group': 'demographics', 'key': 'nationality',      'title': 'حسب الجنسية',        'description': 'توزيع الموظفين حسب الجنسية',     'icon': 'flag',      'color': 'amber'},
    {'group': 'demographics', 'key': 'professions',      'title': 'حسب المهنة',         'description': 'توزيع الموظفين حسب المهنة',      'icon': 'briefcase', 'color': 'amber'},
    {'group': 'demographics', 'key': 'age_distribution', 'title': 'حسب الفئة العمرية',  'description': 'توزيع الموظفين حسب العمر',       'icon': 'cake',      'color': 'amber'},
]


def _grouped_reports():
    grouped = []
    for g in REPORT_GROUPS:
        grouped.append({**g, 'items': [r for r in REPORTS if r.get('group') == g['key']]})
    return grouped


# ══════════════════════════════════════════════════════════════════════════════
# دوال بناء البيانات — كل دالة تُرجع dict بالبيانات اللازمة للقالب
# ══════════════════════════════════════════════════════════════════════════════

def _get_employees():
    from apps.employees.models import Employee
    return Employee.objects.filter(is_deleted=False)


def _active_employees():
    from apps.employees.models import Employee
    return _get_employees().filter(status__in=[Employee.Status.ACTIVE, Employee.Status.LEAVE])


# ── القوى العاملة ──

def _build_headcount_summary(request):
    from apps.employees.models import Employee
    qs = _get_employees()
    statuses = qs.values('status').annotate(count=Count('id')).order_by('-count')
    status_labels = dict(Employee.Status.choices)
    rows = [{'status': status_labels.get(s['status'], s['status']), 'count': s['count']} for s in statuses]
    total = sum(s['count'] for s in rows)
    active = qs.filter(status__in=[Employee.Status.ACTIVE, Employee.Status.LEAVE]).count()
    return {'rows': rows, 'total': total, 'active': active}


def _build_branches(request):
    qs = _active_employees()
    rows = qs.values(name=F('branch__name')).annotate(
        count=Count('id'),
        total_salary=Coalesce(Sum(F('basic_salary') + F('housing_allowance') + F('transport_allowance') + F('other_allowance') + F('cash_amount')), Decimal('0'))
    ).order_by('-count')
    return {'rows': list(rows), 'total': sum(r['count'] for r in rows)}


def _build_departments_overview(request):
    qs = _active_employees()
    rows = qs.values(
        branch_name=F('branch__name'), dept_name=F('department__name')
    ).annotate(count=Count('id')).order_by('branch_name', '-count')
    return {'rows': list(rows)}


def _build_cost_centers_overview(request):
    qs = _active_employees()
    rows = qs.values(
        cc_name=F('cost_center__name'), branch_name=F('branch__name')
    ).annotate(
        count=Count('id'),
        total_salary=Coalesce(Sum(F('basic_salary') + F('housing_allowance') + F('transport_allowance') + F('other_allowance') + F('cash_amount')), Decimal('0'))
    ).order_by('-count')
    return {'rows': list(rows)}


# ── الرواتب ──

def _build_salary_expenses(request):
    qs = _active_employees()
    rows = qs.values(name=F('branch__name')).annotate(
        count=Count('id'),
        basic=Coalesce(Sum('basic_salary'), Decimal('0')),
        housing=Coalesce(Sum('housing_allowance'), Decimal('0')),
        transport=Coalesce(Sum('transport_allowance'), Decimal('0')),
        other=Coalesce(Sum('other_allowance'), Decimal('0')),
        cash=Coalesce(Sum('cash_amount'), Decimal('0')),
    ).order_by('-count')
    for r in rows:
        r['total'] = r['basic'] + r['housing'] + r['transport'] + r['other'] + r['cash']
    rows = list(rows)
    grand = sum(r['total'] for r in rows)
    return {'rows': rows, 'grand_total': grand}


def _build_allowances_breakdown(request):
    qs = _active_employees()
    agg = qs.aggregate(
        housing=Coalesce(Sum('housing_allowance'), Decimal('0')),
        transport=Coalesce(Sum('transport_allowance'), Decimal('0')),
        other=Coalesce(Sum('other_allowance'), Decimal('0')),
        cash=Coalesce(Sum('cash_amount'), Decimal('0')),
    )
    items = [
        {'name': 'بدل سكن', 'amount': agg['housing']},
        {'name': 'بدل نقل', 'amount': agg['transport']},
        {'name': 'بدل إضافي', 'amount': agg['other']},
        {'name': 'كاش', 'amount': agg['cash']},
    ]
    total = sum(i['amount'] for i in items)
    return {'items': items, 'total': total}


def _build_deductions_breakdown(request):
    from apps.payroll.models import PayrollRun
    last_run = PayrollRun.objects.filter(status=PayrollRun.Status.LOCKED).order_by('-period_year', '-period_month').first()
    if not last_run:
        return {'run': None, 'items': [], 'total': Decimal('0')}
    agg = last_run.lines.aggregate(
        absence=Coalesce(Sum('absence_deduction'), Decimal('0')),
        unpaid=Coalesce(Sum('unpaid_leave_deduction'), Decimal('0')),
        loan=Coalesce(Sum('loan_deduction'), Decimal('0')),
        penalty=Coalesce(Sum('penalty_deduction'), Decimal('0')),
        insurance=Coalesce(Sum('insurance_deduction'), Decimal('0')),
        other=Coalesce(Sum('other_deduction'), Decimal('0')),
    )
    items = [
        {'name': 'خصم غياب', 'amount': agg['absence']},
        {'name': 'إجازة بدون راتب', 'amount': agg['unpaid']},
        {'name': 'أقساط سلف', 'amount': agg['loan']},
        {'name': 'مخالفات', 'amount': agg['penalty']},
        {'name': 'تأمينات', 'amount': agg['insurance']},
        {'name': 'خصومات أخرى', 'amount': agg['other']},
    ]
    total = sum(i['amount'] for i in items)
    return {'run': last_run, 'items': items, 'total': total}


def _build_insurance_costs(request):
    qs = _active_employees().exclude(insurance__isnull=True)
    rows = qs.values(
        insurance_name=F('insurance__name'),
        class_name=F('insurance_class__name'),
    ).annotate(count=Count('id')).order_by('-count')
    return {'rows': list(rows), 'total': qs.count()}


# ── الدوران الوظيفي ──

def _build_new_hires(request):
    from apps.employees.models import Employee
    today = date.today()
    start = today - timedelta(days=90)
    qs = _get_employees().filter(hire_date__gte=start).exclude(status=Employee.Status.TERMINATED)
    rows = qs.values('name', 'hire_date', branch_name=F('branch__name')).order_by('-hire_date')
    return {'rows': list(rows), 'total': qs.count(), 'period': f'آخر 90 يوم'}


def _build_terminations(request):
    from apps.employees.models import Employee
    today = date.today()
    start = today - timedelta(days=365)
    qs = _get_employees().filter(status=Employee.Status.TERMINATED, end_date__gte=start)
    rows = qs.values('name', 'end_date', 'end_reason', branch_name=F('branch__name')).order_by('-end_date')
    return {'rows': list(rows), 'total': qs.count(), 'period': f'آخر سنة'}


def _build_turnover_rate(request):
    from apps.employees.models import Employee
    today = date.today()
    start = today - timedelta(days=365)
    hired = _get_employees().filter(hire_date__gte=start).count()
    terminated = _get_employees().filter(status=Employee.Status.TERMINATED, end_date__gte=start).count()
    active = _active_employees().count()
    rate = round((terminated / active * 100), 1) if active > 0 else 0
    return {'hired': hired, 'terminated': terminated, 'active': active, 'rate': rate}


def _build_tenure_analysis(request):
    today = date.today()
    qs = _active_employees().exclude(hire_date__isnull=True)
    brackets = [
        ('أقل من سنة', 0, 365),
        ('1 - 2 سنة', 365, 730),
        ('2 - 5 سنوات', 730, 1825),
        ('5 - 10 سنوات', 1825, 3650),
        ('أكثر من 10 سنوات', 3650, 999999),
    ]
    rows = []
    for label, lo, hi in brackets:
        d_from = today - timedelta(days=hi)
        d_to = today - timedelta(days=lo)
        c = qs.filter(hire_date__gt=d_from, hire_date__lte=d_to).count()
        rows.append({'label': label, 'count': c})
    return {'rows': rows}


# ── الالتزام والوثائق ──

def _build_id_expiry(request):
    today = date.today()
    soon = today + timedelta(days=90)
    qs = _active_employees().exclude(id_number='')
    expired = qs.filter(end_date__lt=today).count()  # تقريبي — حقل انتهاء الهوية غير متاح حالياً
    return {'expired': expired, 'note': 'يعتمد على حقل end_date كتقريب — يُنصح بإضافة حقل id_expiry_date'}


def _build_passport_expiry(request):
    today = date.today()
    soon = today + timedelta(days=90)
    qs = _active_employees().exclude(passport_expiry_date__isnull=True)
    expired = qs.filter(passport_expiry_date__lt=today)
    expiring = qs.filter(passport_expiry_date__gte=today, passport_expiry_date__lte=soon)
    # جمع المنتهي والقارب بـ OR بدلاً من union
    combined = qs.filter(Q(passport_expiry_date__lt=today) | Q(passport_expiry_date__gte=today, passport_expiry_date__lte=soon))
    rows = list(combined.values('name', 'passport_expiry_date', branch_name=F('branch__name')).order_by('passport_expiry_date'))
    return {'rows': rows, 'expired_count': expired.count(), 'expiring_count': expiring.count()}


def _build_health_cards(request):
    today = date.today()
    soon = today + timedelta(days=90)
    qs = _active_employees()
    not_available = qs.filter(health_card_status='not_available').count()
    expired = qs.filter(health_card_expiry__lt=today).count()
    expiring = qs.filter(health_card_expiry__gte=today, health_card_expiry__lte=soon).count()
    available = qs.filter(health_card_status='available', health_card_expiry__gt=soon).count()
    return {'not_available': not_available, 'expired': expired, 'expiring': expiring, 'available': available}


def _build_warnings(request):
    from apps.employees.models import EmployeeStatement
    today = date.today()
    start = today - timedelta(days=365)
    types = [EmployeeStatement.StatementType.WARNING, EmployeeStatement.StatementType.FINAL_WARNING, EmployeeStatement.StatementType.PENALTY]
    qs = EmployeeStatement.objects.filter(statement_type__in=types, statement_date__gte=start, is_deleted=False)
    rows = qs.values(
        emp_name=F('employee__name'), branch_name=F('employee__branch__name'),
    ).annotate(count=Count('id')).order_by('-count')
    type_summary = qs.values('statement_type').annotate(count=Count('id')).order_by('-count')
    labels = dict(EmployeeStatement.StatementType.choices)
    type_rows = [{'type': labels.get(t['statement_type'], t['statement_type']), 'count': t['count']} for t in type_summary]
    return {'rows': list(rows), 'type_rows': type_rows, 'total': qs.count()}


# ── الإجازات ──

def _build_leaves(request):
    from apps.employees.models import EmployeeLeave
    today = date.today()
    start = date(today.year, 1, 1)
    qs = EmployeeLeave.objects.filter(date_from__gte=start, is_deleted=False)
    by_type = qs.values('leave_type').annotate(count=Count('id'), total_days=Coalesce(Sum('days'), Decimal('0'))).order_by('-count')
    labels = dict(EmployeeLeave.LeaveType.choices)
    rows = [{'type': labels.get(r['leave_type'], r['leave_type']), 'count': r['count'], 'days': r['total_days']} for r in by_type]
    return {'rows': rows, 'year': today.year, 'total': qs.count()}


def _build_leave_balance(request):
    qs = _active_employees().exclude(hire_date__isnull=True).exclude(sponsorship__isnull=True).order_by('branch__name', 'name')
    rows = []
    for emp in qs[:200]:
        rows.append({
            'name': emp.name,
            'branch': emp.branch.name if emp.branch else '—',
            'accrued': emp.accrued_leave_days,
            'used': emp.available_leave_balance,
            'remaining': emp.remaining_leave_days,
        })
    return {'rows': rows}


def _build_absences(request):
    from apps.employees.models import EmployeeAbsence
    today = date.today()
    start = date(today.year, 1, 1)
    qs = EmployeeAbsence.objects.filter(absence_date__gte=start, is_deleted=False)
    rows = qs.values(
        emp_name=F('employee__name'), branch_name=F('employee__branch__name')
    ).annotate(
        total_days=Coalesce(Sum('days'), Decimal('0')),
        total_deduction=Coalesce(Sum('deduction_amount'), Decimal('0')),
        count=Count('id'),
    ).order_by('-total_days')
    return {'rows': list(rows), 'year': today.year}


# ── ديموغرافيا ──

def _build_gender(request):
    from apps.employees.models import Employee
    qs = _active_employees()
    rows = qs.values('gender').annotate(count=Count('id')).order_by('-count')
    labels = dict(Employee.Gender.choices)
    result = [{'label': labels.get(r['gender'], r['gender'] or 'غير محدد'), 'count': r['count']} for r in rows]
    total = sum(r['count'] for r in result)
    return {'rows': result, 'total': total}


def _build_nationality(request):
    qs = _active_employees()
    rows = qs.values(label=Coalesce(F('nationality__name'), Value('غير محدد'))).annotate(count=Count('id')).order_by('-count')
    return {'rows': list(rows)}


def _build_professions(request):
    qs = _active_employees()
    rows = qs.values(label=Coalesce(F('profession__name'), Value('غير محدد'))).annotate(count=Count('id')).order_by('-count')
    return {'rows': list(rows)}


def _build_age_distribution(request):
    today = date.today()
    qs = _active_employees().exclude(hire_date__isnull=True)
    # لا يوجد حقل birth_date حالياً — نستخدم hire_date كبديل
    return {'rows': [], 'note': 'لا يوجد حقل تاريخ الميلاد حالياً. يُنصح بإضافة حقل birth_date للحصول على تقرير دقيق.'}


# ══════════════════════════════════════════════════════════════════════════════
# ربط المفاتيح بدوال البناء
# ══════════════════════════════════════════════════════════════════════════════

BUILDERS = {
    'headcount_summary': _build_headcount_summary,
    'branches': _build_branches,
    'departments_overview': _build_departments_overview,
    'cost_centers_overview': _build_cost_centers_overview,
    'salary_expenses': _build_salary_expenses,
    'allowances_breakdown': _build_allowances_breakdown,
    'deductions_breakdown': _build_deductions_breakdown,
    'insurance_costs': _build_insurance_costs,
    'new_hires': _build_new_hires,
    'terminations': _build_terminations,
    'turnover_rate': _build_turnover_rate,
    'tenure_analysis': _build_tenure_analysis,
    'id_expiry': _build_id_expiry,
    'passport_expiry': _build_passport_expiry,
    'health_cards': _build_health_cards,
    'warnings': _build_warnings,
    'leaves': _build_leaves,
    'leave_balance': _build_leave_balance,
    'absences': _build_absences,
    'gender': _build_gender,
    'nationality': _build_nationality,
    'professions': _build_professions,
    'age_distribution': _build_age_distribution,
}


# ══════════════════════════════════════════════════════════════════════════════
# Views
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@permission_required('reports.view')
def reports_index(request):
    return render(request, 'pages/reports/index.html', {
        'report_groups': _grouped_reports(),
        'reports': REPORTS,
    })


@login_required
@permission_required('reports.view')
def report_detail(request, report_type):
    report_meta = next((r for r in REPORTS if r['key'] == report_type), None)
    if not report_meta:
        raise Http404("تقرير غير معروف")

    group_meta = next((g for g in REPORT_GROUPS if g['key'] == report_meta.get('group')), None)
    siblings = [r for r in REPORTS if r.get('group') == report_meta.get('group') and r['key'] != report_type]

    # بناء البيانات الفعلية
    builder = BUILDERS.get(report_type)
    report_data = builder(request) if builder else {}

    return render(request, 'pages/reports/detail.html', {
        'report_meta': report_meta,
        'group_meta': group_meta,
        'siblings': siblings,
        'reports': REPORTS,
        'data': report_data,
        'report_type': report_type,
    })
