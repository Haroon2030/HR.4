"""
التقارير — صفحات عرض التقارير الفرعية
حالياً: شاشات Placeholder بدون منطق بناء بعد
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import Http404

from apps.core.web_views._helpers import admin_required
from apps.core.decorators import permission_required


# مجموعات التقارير المترابطة
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


# قائمة التقارير المعتمدة (مرتبطة بالمجموعات أعلاه)
REPORTS = [
    # ── القوى العاملة ─────────────────────────────────────────
    {'group': 'workforce', 'key': 'headcount_summary',  'title': 'ملخص القوى العاملة',  'description': 'إجمالي الموظفين النشطين مع مؤشرات النمو',          'icon': 'users-round',  'color': 'primary'},
    {'group': 'workforce', 'key': 'branches',           'title': 'الموظفون حسب الفروع', 'description': 'توزيع وأعداد الموظفين على كل فرع',                 'icon': 'building-2',   'color': 'primary'},
    {'group': 'workforce', 'key': 'departments_overview', 'title': 'الموظفون حسب الأقسام', 'description': 'توزيع الموظفين على الأقسام داخل الفروع',         'icon': 'network',      'color': 'primary'},
    {'group': 'workforce', 'key': 'cost_centers_overview', 'title': 'الموظفون حسب مراكز التكلفة', 'description': 'توزيع الموظفين والتكلفة على مراكز التكلفة', 'icon': 'layers',       'color': 'primary'},

    # ── الرواتب والمصاريف ───────────────────────────────────
    {'group': 'salary',    'key': 'salary_expenses',    'title': 'إجمالي مصاريف الرواتب', 'description': 'إجمالي الرواتب الشهرية والسنوية حسب الفرع/القسم', 'icon': 'wallet',       'color': 'emerald'},
    {'group': 'salary',    'key': 'allowances_breakdown', 'title': 'تفصيل البدلات',       'description': 'تحليل تفصيلي لجميع أنواع البدلات الممنوحة',         'icon': 'plus-circle',  'color': 'emerald'},
    {'group': 'salary',    'key': 'deductions_breakdown', 'title': 'تفصيل الاستقطاعات',   'description': 'تحليل تفصيلي لجميع الاستقطاعات والخصومات',          'icon': 'minus-circle', 'color': 'emerald'},
    {'group': 'salary',    'key': 'insurance_costs',    'title': 'مصاريف التأمينات',     'description': 'تكلفة التأمينات الاجتماعية والصحية على المنشأة',     'icon': 'shield',       'color': 'emerald'},

    # ── الدوران الوظيفي ─────────────────────────────────────
    {'group': 'turnover',  'key': 'new_hires',          'title': 'التعيينات الجديدة',     'description': 'الموظفون المعينون حديثاً ضمن فترة محددة',           'icon': 'user-plus',    'color': 'indigo'},
    {'group': 'turnover',  'key': 'terminations',       'title': 'إنهاء الخدمات',         'description': 'الموظفون المنتهية خدماتهم وأسباب الإنهاء',          'icon': 'user-minus',   'color': 'indigo'},
    {'group': 'turnover',  'key': 'turnover_rate',      'title': 'معدل الدوران الوظيفي',  'description': 'مقارنة بين التعيينات والإنهاءات وحساب معدل الدوران', 'icon': 'refresh-cw',  'color': 'indigo'},
    {'group': 'turnover',  'key': 'tenure_analysis',    'title': 'تحليل فترة الخدمة',     'description': 'متوسط فترة بقاء الموظفين وتوزيعهم حسب سنوات الخدمة', 'icon': 'hourglass',   'color': 'indigo'},

    # ── الالتزام والوثائق ──────────────────────────────────
    {'group': 'compliance','key': 'id_expiry',          'title': 'انتهاء الهويات',        'description': 'الهويات الوطنية/الإقامات المنتهية أو القاربة على الانتهاء', 'icon': 'id-card',  'color': 'rose'},
    {'group': 'compliance','key': 'passport_expiry',    'title': 'انتهاء الجوازات',       'description': 'الجوازات المنتهية أو القاربة على الانتهاء',          'icon': 'book-open',    'color': 'rose'},
    {'group': 'compliance','key': 'health_cards',       'title': 'الكروت الصحية',         'description': 'متابعة الكروت الصحية وانتهاء صلاحياتها',             'icon': 'heart-pulse',  'color': 'rose'},
    {'group': 'compliance','key': 'insurance_expiry',   'title': 'انتهاء التأمينات',      'description': 'وثائق التأمين المنتهية أو القاربة على الانتهاء',     'icon': 'shield-alert', 'color': 'rose'},
    {'group': 'compliance','key': 'warnings',           'title': 'الإنذارات والمخالفات',  'description': 'الإنذارات والمخالفات الصادرة للموظفين',              'icon': 'alert-triangle','color': 'rose'},

    # ── الإجازات والغياب ────────────────────────────────────
    {'group': 'leaves',    'key': 'leaves',             'title': 'الإجازات الممنوحة',     'description': 'تقرير عام عن الإجازات الممنوحة بأنواعها',           'icon': 'plane',        'color': 'cyan'},
    {'group': 'leaves',    'key': 'leave_balance',      'title': 'رصيد الإجازات',         'description': 'الرصيد المتاح من الإجازات لكل موظف',                'icon': 'calendar-clock','color': 'cyan'},
    {'group': 'leaves',    'key': 'absences',           'title': 'تقرير الغياب',          'description': 'إحصائيات الغياب حسب الفرع والموظف',                 'icon': 'user-x',       'color': 'cyan'},

    # ── ديموغرافيا ──────────────────────────────────────────
    {'group': 'demographics','key': 'gender',           'title': 'حسب الجنس',             'description': 'توزيع الموظفين حسب الجنس',                          'icon': 'users',        'color': 'amber'},
    {'group': 'demographics','key': 'nationality',      'title': 'حسب الجنسية',           'description': 'توزيع الموظفين حسب الجنسية',                        'icon': 'flag',         'color': 'amber'},
    {'group': 'demographics','key': 'professions',      'title': 'حسب المهنة',            'description': 'توزيع الموظفين حسب المهنة',                         'icon': 'briefcase',    'color': 'amber'},
    {'group': 'demographics','key': 'age_distribution', 'title': 'حسب الفئة العمرية',     'description': 'توزيع الموظفين حسب الفئات العمرية',                 'icon': 'cake',         'color': 'amber'},
]


def _grouped_reports():
    """يرجع المجموعات وكل مجموعة معها قائمة تقاريرها"""
    grouped = []
    for g in REPORT_GROUPS:
        grouped.append({
            **g,
            'items': [r for r in REPORTS if r.get('group') == g['key']],
        })
    return grouped


@login_required
@permission_required('reports.view')
def reports_index(request):
    """الصفحة الرئيسية لقسم التقارير — مجموعات تقارير مترابطة"""
    return render(request, 'pages/reports/index.html', {
        'report_groups': _grouped_reports(),
        'reports': REPORTS,
    })


@login_required
@permission_required('reports.view')
def report_detail(request, report_type):
    """شاشة تقرير فرعي (Placeholder حالياً — قيد الإنشاء)"""
    report_meta = next((r for r in REPORTS if r['key'] == report_type), None)
    if not report_meta:
        raise Http404("تقرير غير معروف")

    group_meta = next((g for g in REPORT_GROUPS if g['key'] == report_meta.get('group')), None)
    siblings = [r for r in REPORTS if r.get('group') == report_meta.get('group') and r['key'] != report_type]

    return render(request, 'pages/reports/_placeholder.html', {
        'report_meta': report_meta,
        'group_meta': group_meta,
        'siblings': siblings,
        'reports': REPORTS,
    })
