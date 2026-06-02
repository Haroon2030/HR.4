"""فهرس التقارير — دمج القائمة الأساسية مع التقارير المطلوبة دون تكرار بالاسم."""

from __future__ import annotations


def _norm_title(title: str) -> str:
    """تطبيع بسيط للعربية لمقارنة العناوين."""
    t = (title or '').strip()
    for src, dst in (
        ('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ة', 'ه'),
        ('ى', 'ي'),
    ):
        t = t.replace(src, dst)
    return ' '.join(t.split())


# التقارير المطلوبة (من قائمة العميل) — تُدمَج مع الموجود: نفس المفتاح يُحدَّث العنوان ولا يُكرَّر
PRIMARY_REPORT_SPECS = [
    {
        'key': 'employees',
        'title': 'الموظفين',
        'group': 'primary',
        'icon': 'users',
        'color': 'primary',
        'description': 'قائمة جميع الموظفين مع الحالة والفرع',
    },
    {
        'key': 'stopped',
        'title': 'متوقف / مع إظهار السبب',
        'group': 'primary',
        'icon': 'user-x',
        'color': 'rose',
        'description': 'الموظفون المنتهية خدمتهم مع سبب التوقف',
    },
    {
        'merge_key': 'salary_expenses',
        'title': 'تفاصيل الراتب',
        'group': 'primary',
        'icon': 'wallet',
        'color': 'emerald',
        'description': 'رواتب كل موظف بالتفصيل',
    },
    {
        'merge_key': 'warnings',
        'title': 'الإنذارات',
        'group': 'primary',
        'icon': 'alert-triangle',
        'color': 'rose',
        'description': 'إنذارات ومخالفات الموظفين',
    },
    {
        'key': 'statements',
        'title': 'الإفادات',
        'group': 'primary',
        'icon': 'file-text',
        'color': 'blue',
        'description': 'إفادات وإقرارات الموظفين',
    },
    {
        'merge_key': 'absences',
        'title': 'الغيابات / مع إظهار السبب',
        'group': 'primary',
        'icon': 'user-x',
        'color': 'cyan',
        'description': 'سجلات الغياب مع سبب الغياب',
    },
    {
        'merge_key': 'leave_balance',
        'title': 'رصيد الأجازات',
        'group': 'primary',
        'icon': 'calendar-clock',
        'color': 'cyan',
        'description': 'رصيد إجازات كل موظف',
    },
    {
        'merge_key': 'gender',
        'title': 'الجنس',
        'group': 'primary',
        'icon': 'users',
        'color': 'amber',
        'description': 'الموظفون حسب الجنس',
    },
    {
        'merge_key': 'nationality',
        'title': 'الجنسية',
        'group': 'primary',
        'icon': 'flag',
        'color': 'amber',
        'description': 'الموظفون حسب الجنسية',
    },
    {
        'merge_key': 'professions',
        'title': 'المهنة',
        'group': 'primary',
        'icon': 'briefcase',
        'color': 'amber',
        'description': 'الموظفون حسب المهنة',
    },
    {
        'key': 'housing',
        'title': 'السكن',
        'group': 'primary',
        'icon': 'home',
        'color': 'amber',
        'description': 'توزيع الموظفين على السكن',
    },
    {
        'key': 'active_headcount',
        'title': 'رأس العمل',
        'group': 'primary',
        'icon': 'user-check',
        'color': 'emerald',
        'description': 'الموظفون على رأس العمل',
    },
    {
        'key': 'suspended',
        'title': 'الموقوفين',
        'group': 'primary',
        'icon': 'user-minus',
        'color': 'orange',
        'description': 'الموظفون الموقوفون',
    },
    {
        'key': 'attendance_late',
        'title': 'التأخر (حضور وانصراف)',
        'group': 'primary',
        'icon': 'clock',
        'color': 'violet',
        'description': 'تأخر الدخول والخروج المبكر من البصمة',
    },
]


def merge_reports_catalog(base_reports: list[dict], primary_specs: list[dict]) -> list[dict]:
    """
    يدمج التقارير الأساسية مع القائمة المطلوبة:
    - إن وُجد merge_key أو key مطابق → يُحدَّث العنوان والمجموعة دون تكرار
    - إن تطابق العنوان (بعد التطبيع) → يُتخطى التكرار
    """
    by_key = {r['key']: dict(r) for r in base_reports}
    merged: list[dict] = []
    seen_keys: set[str] = set()
    seen_titles: set[str] = set()

    for spec in primary_specs:
        merge_key = spec.get('merge_key') or spec.get('key')
        if not merge_key:
            continue
        base = by_key.get(merge_key)
        if base:
            entry = {**base, **{k: v for k, v in spec.items() if k != 'merge_key'}}
            entry['key'] = merge_key
        else:
            entry = {k: v for k, v in spec.items() if k != 'merge_key'}
            entry.setdefault('group', 'primary')
            entry.setdefault('icon', 'file-bar-chart')
            entry.setdefault('color', 'primary')
            entry.setdefault('description', entry.get('title', ''))

        title_norm = _norm_title(entry['title'])
        if entry['key'] in seen_keys or title_norm in seen_titles:
            continue
        merged.append(entry)
        seen_keys.add(entry['key'])
        seen_titles.add(title_norm)

    for report in base_reports:
        if report['key'] in seen_keys:
            continue
        title_norm = _norm_title(report['title'])
        if title_norm in seen_titles:
            continue
        merged.append(report)
        seen_keys.add(report['key'])
        seen_titles.add(title_norm)

    return merged
