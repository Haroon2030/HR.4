"""
التقارير — صفحات عرض التقارير الفرعية
حالياً: شاشات Placeholder بدون منطق بناء بعد
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import Http404

from apps.core.web_views._helpers import admin_required


# قائمة التقارير المعتمدة
REPORTS = [
    {'key': 'branches',         'title': 'تقرير الفروع',       'description': 'إحصائيات وتوزيع الموظفين على الفروع', 'icon': 'building-2',     'color': 'primary'},
    {'key': 'salary_expenses',  'title': 'مصاريف الرواتب',     'description': 'تفصيل مصاريف الرواتب والبدلات والاستقطاعات', 'icon': 'wallet',     'color': 'emerald'},
    {'key': 'leaves',           'title': 'الإجازات',           'description': 'تقرير عام عن الإجازات الممنوحة',         'icon': 'plane',         'color': 'cyan'},
    {'key': 'terminations',     'title': 'إنهاء الخدمات',      'description': 'تقرير الموظفين المنتهية خدماتهم',        'icon': 'user-minus',    'color': 'rose'},
    {'key': 'new_hires',        'title': 'الموظفين الجدد',     'description': 'الموظفون المعيّنون حديثاً ضمن فترة محددة', 'icon': 'user-plus',     'color': 'emerald'},
    {'key': 'absences',         'title': 'تقرير الغياب',       'description': 'إحصائيات الغياب حسب الفرع والموظف',      'icon': 'user-x',        'color': 'amber'},
    {'key': 'leave_balance',    'title': 'رصيد الإجازات',      'description': 'الرصيد المتاح من الإجازات لكل موظف',     'icon': 'calendar-clock','color': 'cyan'},
    {'key': 'professions',      'title': 'المهن',              'description': 'توزيع الموظفين حسب المهنة',              'icon': 'briefcase',     'color': 'primary'},
    {'key': 'gender',           'title': 'الجنس',              'description': 'توزيع الموظفين حسب الجنس',               'icon': 'users',         'color': 'pink'},
    {'key': 'nationality',      'title': 'الجنسية',            'description': 'توزيع الموظفين حسب الجنسية',             'icon': 'flag',          'color': 'amber'},
    {'key': 'health_cards',     'title': 'الكروت الصحية',      'description': 'متابعة الكروت الصحية وانتهاء صلاحياتها', 'icon': 'heart-pulse',   'color': 'rose'},
    {'key': 'warnings',         'title': 'الإنذارات',          'description': 'الإنذارات والمخالفات الصادرة للموظفين',   'icon': 'alert-triangle','color': 'amber'},
]


@login_required
@admin_required
def reports_index(request):
    """الصفحة الرئيسية لقسم التقارير — شبكة بطاقات للتقارير الفرعية"""
    return render(request, 'pages/reports/index.html', {
        'reports': REPORTS,
    })


@login_required
@admin_required
def report_detail(request, report_type):
    """شاشة تقرير فرعي (Placeholder حالياً — قيد الإنشاء)"""
    report_meta = next((r for r in REPORTS if r['key'] == report_type), None)
    if not report_meta:
        raise Http404("تقرير غير معروف")

    return render(request, 'pages/reports/_placeholder.html', {
        'report_meta': report_meta,
        'reports': REPORTS,
    })
