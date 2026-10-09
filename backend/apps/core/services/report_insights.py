"""القراءة الإدارية — جمل تحليلية ومؤشرات ورسوم تُولَّد من بيانات التقارير (لا نصوص ثابتة)."""
from __future__ import annotations

import re
from collections import Counter
from datetime import date

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

_MONTHS_AR = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
_PREFERRED_CATEGORY_HEADERS = ('الحالة', 'الفرع', 'القسم', 'الجنس', 'الجنسية', 'المهنة', 'الإدارة', 'نوع')
_ID_HEADERS = ('رقم', 'الرقم', 'معرف', 'هوية', 'التاريخ', 'تاريخ', 'جوال', 'الجوال', 'هاتف', 'الهاتف', 'آيبان', 'ايبان', 'حساب', 'بريد')
_NUMBER_RE = re.compile(r'^-?\d[\d,]*(\.\d+)?$')
_EMPTY = ('', '—', '-', 'None', None)

_GENDER_LABELS = {'male': 'ذكور', 'female': 'إناث'}
_DONUT_COLORS = ['#2563eb', '#059669', '#d97706', '#7c3aed', '#e11d48', '#0891b2', '#64748b']


def _to_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace('٬', ',')
    if _NUMBER_RE.match(text):
        return float(text.replace(',', ''))
    return None


def _is_empty(value) -> bool:
    return value in _EMPTY or (isinstance(value, str) and not value.strip())


def _pct(part: float, whole: float) -> int:
    return int(round(part * 100 / whole)) if whole else 0


def _fmt(n: float) -> str:
    return f'{n:,.0f}' if abs(n - round(n)) < 0.005 else f'{n:,.1f}'


def analyze_table(columns: list[str], rows: list[list]) -> dict:
    """يحلّل جدول تقرير: مؤشرات + جمل إدارية + مواصفة رسم بياني (توزيع أفضل عمود تصنيفي)."""
    total = len(rows)
    result = {
        'kpis': [{'label': 'عدد السجلات', 'value': f'{total:,}'}], 'insights': [], 'chart': None,
        'numeric_columns': [], 'totals': [],
    }
    if not total or not columns:
        result['insights'].append({'tone': 'info', 'text': 'لا توجد بيانات ضمن الشروط المحددة. وسّع الفترة أو النطاق.'})
        return result

    cols = []
    for idx, name in enumerate(columns):
        values = [r[idx] if idx < len(r) else None for r in rows]
        filled = [v for v in values if not _is_empty(v)]
        numeric = [n for n in (_to_number(v) for v in filled) if n is not None]
        # أرقام طويلة بلا كسور (جوال/هوية/حساب) معرّفات لا قيم تُجمع
        looks_like_id = bool(filled) and (
            sum(1 for v in filled if re.fullmatch(r'0?\d{7,}', str(v).strip())) / len(filled) >= 0.6
        )
        cols.append({
            'idx': idx, 'name': str(name), 'values': values, 'filled': filled,
            'numeric': numeric,
            'is_numeric': bool(filled) and len(numeric) / len(filled) >= 0.8
            and not looks_like_id
            and not any(h in str(name) for h in _ID_HEADERS),
            'unique': len({str(v) for v in filled}),
        })

    result['numeric_columns'] = [c['idx'] for c in cols if c['is_numeric'] and len(c['numeric']) >= 2]
    if result['numeric_columns'] and total >= 2:
        sums = {c['idx']: sum(c['numeric']) for c in cols if c['idx'] in result['numeric_columns']}
        result['totals'] = [_fmt(sums[i]) if i in sums else '' for i in range(len(columns))]

    # ── عمود تصنيفي للتوزيع ──
    categorical = [
        c for c in cols
        if not c['is_numeric'] and 2 <= c['unique'] <= min(12, max(total - 1, 2))
        and len(c['filled']) >= total * 0.5
        and not any(h in c['name'] for h in _ID_HEADERS)
    ]
    categorical.sort(key=lambda c: (
        0 if any(h in c['name'] for h in _PREFERRED_CATEGORY_HEADERS) else 1, c['unique'],
    ))
    if categorical:
        cat = categorical[0]
        counter = Counter(str(v) for v in cat['filled'])
        top = counter.most_common(8)
        top_label, top_count = top[0]
        share = _pct(top_count, len(cat['filled']))
        tone = 'warn' if share >= 60 and cat['unique'] > 2 else 'info'
        result['insights'].append({
            'tone': tone,
            'text': f'«{top_label}» هو الأكثر في «{cat["name"]}»: {top_count:,} سجل ({share}%) من أصل {len(cat["filled"]):,}.'
                    + (' التركّز مرتفع، راجع التوزيع.' if tone == 'warn' else ''),
        })
        if len(top) > 1:
            low_label, low_count = top[-1]
            result['insights'].append({
                'tone': 'info',
                'text': f'الأقل حضوراً: «{low_label}» بـ {low_count:,} سجل ({_pct(low_count, len(cat["filled"]))}%).',
            })
        result['chart'] = {
            'title': f'توزيع السجلات حسب {cat["name"]}',
            'items': [{'label': k, 'value': v, 'pct': _pct(v, len(cat['filled']))} for k, v in top],
        }

    # ── أعمدة رقمية: إجمالي ومتوسط وأعلى قيمة ──
    numeric_cols = [c for c in cols if c['is_numeric'] and len(c['numeric']) >= 2][:2]
    for c in numeric_cols:
        s = sum(c['numeric'])
        avg = s / len(c['numeric'])
        peak = max(c['numeric'])
        result['kpis'].append({'label': f'إجمالي {c["name"]}', 'value': _fmt(s)})
        result['insights'].append({
            'tone': 'info',
            'text': f'إجمالي «{c["name"]}» {_fmt(s)} بمتوسط {_fmt(avg)} للسجل، وأعلى قيمة {_fmt(peak)}.',
        })

    # ── جودة البيانات ──
    gaps = [(c['name'], total - len(c['filled'])) for c in cols if total - len(c['filled']) >= total * 0.4]
    if gaps:
        name, missing = max(gaps, key=lambda g: g[1])
        result['insights'].append({
            'tone': 'warn',
            'text': f'«{name}» فارغ في {missing:,} سجل ({_pct(missing, total)}%)، بيانات ناقصة تحتاج استكمالاً.',
        })

    if len(result['insights']) == 0:
        result['insights'].append({'tone': 'info', 'text': f'التقرير يضم {total:,} سجلاً، ولا توجد مؤشرات تجميعية ظاهرة.'})
    return result


def _month_floor(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, delta: int) -> date:
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def executive_overview(emp_qs, *, date_from: date, date_to: date, branch_ids, open_requests: dict) -> dict:
    """نظرة تنفيذية للقوى العاملة ضمن النطاق: مؤشرات + رسوم + قراءة إدارية.

    emp_qs: موظفون (غير محذوفين) بعد تطبيق فلتر الفروع/الكفالة. open_requests: {'employment': n, 'operations': n}.
    """
    from apps.employees.models import Employee

    stats = emp_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status=Employee.Status.ACTIVE)),
        leave=Count('id', filter=Q(status=Employee.Status.LEAVE)),
        suspended=Count('id', filter=Q(status=Employee.Status.SUSPENDED)),
        terminated=Count('id', filter=Q(status=Employee.Status.TERMINATED)),
        hires=Count('id', filter=Q(hire_date__gte=date_from, hire_date__lte=date_to)),
        exits=Count('id', filter=Q(status=Employee.Status.TERMINATED, end_date__gte=date_from, end_date__lte=date_to)),
    )
    current = (stats['active'] or 0) + (stats['leave'] or 0)
    total = stats['total'] or 0
    hires = stats['hires'] or 0
    exits = stats['exits'] or 0

    # ── سلسلة آخر 6 أشهر (تعيين مقابل إنهاء) ──
    end_month = _month_floor(date_to)
    first_month = _add_months(end_month, -5)
    hire_rows = (
        emp_qs.filter(hire_date__gte=first_month, hire_date__lt=_add_months(end_month, 1))
        .annotate(m=TruncMonth('hire_date')).values('m').annotate(c=Count('id'))
    )
    exit_rows = (
        emp_qs.filter(status=Employee.Status.TERMINATED, end_date__gte=first_month, end_date__lt=_add_months(end_month, 1))
        .annotate(m=TruncMonth('end_date')).values('m').annotate(c=Count('id'))
    )
    hires_by = {(r['m'].year, r['m'].month): r['c'] for r in hire_rows if r['m']}
    exits_by = {(r['m'].year, r['m'].month): r['c'] for r in exit_rows if r['m']}
    series = []
    for i in range(6):
        m = _add_months(first_month, i)
        series.append({
            'label': _MONTHS_AR[m.month - 1],
            'hires': hires_by.get((m.year, m.month), 0),
            'exits': exits_by.get((m.year, m.month), 0),
        })
    series_max = max([max(s['hires'], s['exits']) for s in series] + [1])
    for s in series:
        s['hires_h'] = int(s['hires'] * 100 / series_max)
        s['exits_h'] = int(s['exits'] * 100 / series_max)

    # ── توزيع الفروع والنوع ──
    branch_rows = list(
        emp_qs.exclude(status=Employee.Status.TERMINATED)
        .values('branch__name').annotate(c=Count('id')).order_by('-c')[:6]
    )
    branch_max = max([b['c'] for b in branch_rows] + [1])
    branches = [{
        'label': b['branch__name'] or 'بدون فرع', 'value': b['c'],
        'pct': _pct(b['c'], current), 'width': int(b['c'] * 100 / branch_max),
    } for b in branch_rows]

    gender_rows = list(
        emp_qs.exclude(status=Employee.Status.TERMINATED).values('gender').annotate(c=Count('id')).order_by('-c')
    )
    gender_total = sum(g['c'] for g in gender_rows) or 1
    donut, start = [], 0.0
    gender = []
    for i, g in enumerate(gender_rows):
        color = _DONUT_COLORS[i % len(_DONUT_COLORS)]
        share = g['c'] * 100 / gender_total
        donut.append(f'{color} {start:.2f}% {start + share:.2f}%')
        start += share
        gender.append({'label': _GENDER_LABELS.get(g['gender'], 'غير محدد'), 'value': g['c'], 'pct': int(round(share)), 'color': color})
    donut_style = f'conic-gradient({", ".join(donut)})' if donut else 'conic-gradient(#e2e8f0 0 100%)'

    # ── القراءة الإدارية ──
    insights = []
    if total:
        insights.append({
            'tone': 'info',
            'text': f'القوى العاملة الحالية {current:,} موظفاً من أصل {total:,} سجلاً، '
                    f'ويشكّل من هم على رأس العمل {_pct(stats["active"] or 0, current or 1)}% منهم.',
        })
    net = hires - exits
    if hires or exits:
        tone = 'good' if net > 0 else ('warn' if net < 0 else 'info')
        verdict = 'نمو صافٍ' if net > 0 else ('تراجع صافٍ' if net < 0 else 'استقرار')
        insights.append({
            'tone': tone,
            'text': f'خلال الفترة: {hires:,} تعيين مقابل {exits:,} إنهاء خدمة، {verdict}'
                    + (f' بمقدار {abs(net):,}.' if net else '.'),
        })
    else:
        insights.append({'tone': 'info', 'text': 'لا تعيينات ولا إنهاء خدمات مسجلة خلال الفترة المحددة.'})
    if current and (stats['exits'] or 0):
        rate = exits * 100 / current
        insights.append({
            'tone': 'warn' if rate >= 5 else 'info',
            'text': f'معدل الدوران في الفترة {rate:.1f}% من القوى العاملة'
                    + (' وهو مرتفع ويستحق مراجعة الأسباب.' if rate >= 5 else '.'),
        })
    if branches and current:
        top = branches[0]
        if top['pct'] >= 40 and len(branches) > 1:
            insights.append({'tone': 'warn', 'text': f'«{top["label"]}» يضم {top["pct"]}% من الموظفين، تركّز مرتفع في فرع واحد.'})
        else:
            insights.append({'tone': 'info', 'text': f'أكبر الفروع «{top["label"]}» بـ {top["value"]:,} موظفاً ({top["pct"]}%).'})
    on_leave = stats['leave'] or 0
    if on_leave:
        insights.append({'tone': 'info', 'text': f'{on_leave:,} موظف في إجازة حالياً ({_pct(on_leave, current or 1)}% من القوى العاملة).'})
    backlog = (open_requests.get('employment') or 0) + (open_requests.get('operations') or 0)
    if backlog:
        insights.append({
            'tone': 'warn',
            'text': f'{backlog:,} طلب بانتظار الإجراء ({open_requests.get("operations", 0):,} عمليات و{open_requests.get("employment", 0):,} توظيف).',
        })
    else:
        insights.append({'tone': 'good', 'text': 'لا توجد طلبات عمليات أو توظيف معلّقة.'})

    kpis = [
        {'label': 'القوى العاملة', 'value': f'{current:,}', 'tone': 'blue', 'icon': 'users'},
        {'label': 'تعيينات الفترة', 'value': f'{hires:,}', 'tone': 'emerald', 'icon': 'user-plus'},
        {'label': 'إنهاء خدمات', 'value': f'{exits:,}', 'tone': 'rose', 'icon': 'user-minus'},
        {'label': 'في إجازة', 'value': f'{on_leave:,}', 'tone': 'cyan', 'icon': 'plane'},
        {'label': 'موقوفون', 'value': f'{stats["suspended"] or 0:,}', 'tone': 'amber', 'icon': 'pause-circle'},
        {'label': 'طلبات معلّقة', 'value': f'{backlog:,}', 'tone': 'violet', 'icon': 'inbox'},
    ]
    return {
        'kpis': kpis, 'insights': insights, 'series': series, 'branches': branches,
        'gender': gender, 'donut_style': donut_style, 'gender_total': gender_total if gender_rows else 0,
        'current': current,
    }


_TONE_TOKENS = (
    ('bad', ('خطأ', 'مرفوض', 'منتهي', 'غير مربوط', 'ملغ', 'غير متصل', 'متأخر', 'مخالفة')),
    ('warn', ('بصمة واحدة', 'غير مكتمل', 'معلق', 'معلّق', 'بانتظار', 'قيد', 'موقوف', 'إجازة', 'تحتاج')),
    ('good', ('متصل', 'مكتمل', 'نشط', 'رأس العمل', 'مقبول', 'معتمد', 'مدفوع', 'منفَّذ', 'مُنفَّذ', 'يعمل', 'مربوط')),
)
_STATUS_HEADERS = ('الحالة', 'حالة')


def decorate_rows(columns: list[str], rows: list[list], numeric_columns: list[int]) -> list[list[dict]]:
    """يجهّز خلايا العرض: نغمة لونية لأعمدة الحالة وعلم للأعمدة الرقمية (محاذاة أرقام)."""
    status_cols = {i for i, c in enumerate(columns) if any(h in str(c) for h in _STATUS_HEADERS)}
    numeric = set(numeric_columns)
    out = []
    for row in rows:
        cells = []
        for i, value in enumerate(row):
            cell = {'v': value, 'tone': '', 'num': i in numeric}
            if i in status_cols and not _is_empty(value):
                text = str(value)
                for tone, tokens in _TONE_TOKENS:
                    if any(t in text for t in tokens):
                        cell['tone'] = tone
                        break
            cells.append(cell)
        out.append(cells)
    return out
