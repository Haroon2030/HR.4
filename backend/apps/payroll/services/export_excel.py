"""تصدير مسير الرواتب إلى Excel — تنسيق كشف الرواتب (صف ترويسة + بيانات)."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.utils import timezone

from dataclasses import dataclass

from apps.payroll.models import PayrollLine
from apps.payroll.services.payroll_line_columns import (
    HEADER_FILL_COLORS,
    MONEY_SUM_KEYS,
    PAYROLL_LINE_COLUMNS,
    build_ephemeral_payroll_line,
    lookup_source_payroll_line,
    payroll_lines_select_related,
    resolve_cell_value,
    resolve_detailed_allocation_cell_value,
)

PAYROLL_EXPORT_COLUMNS = PAYROLL_LINE_COLUMNS

COLUMN_WIDTHS = {
    'employee_number': 12,
    'employee_name': 22,
    'account_number': 24,
    'bank': 14,
    'account_type': 12,
    'salary_gross': 11,
    'id_number': 14,
    'branch': 12,
    'company': 16,
    'period_start': 12,
    'period_end': 12,
    'worked_days': 10,
    'basic_salary': 12,
    'earned_basic': 12,
    'housing_allowance': 11,
    'earned_housing': 13,
    'transport_allowance': 11,
    'fixed_other_allowance': 12,
    'additional': 10,
    'total_allowances': 12,
    'total_earnings': 14,
    'penalties_deductions': 14,
    'insurance_deduction': 16,
    'loan_deduction': 14,
    'total_deductions': 13,
    'net_salary': 11,
    'payment': 10,
}

ROW_HEIGHT = 18


def _money(val) -> float:
    if val is None or val == '':
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def _write_payroll_sheet(ws, line_pairs, *, meta_note: str, resolve_value=None):
    """يكتب ترويسة وصفوف وإجماليات على ورقة واحدة. line_pairs: [(run, line), ...]."""
    get_cell_value = resolve_value or resolve_cell_value
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    thin = Side(border_style='thin', color='000000')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    align_right = Alignment(horizontal='right', vertical='center', wrap_text=False)
    header_font = Font(name='Arial', size=9, bold=True, color='000000')
    data_font = Font(name='Arial', size=9, color='000000')
    total_font = Font(name='Arial', size=9, bold=True, color='000000')

    header_row = 1
    data_start = 2

    for idx, (key, label, color_key, _col_type) in enumerate(PAYROLL_EXPORT_COLUMNS, start=1):
        fill = PatternFill('solid', fgColor=HEADER_FILL_COLORS.get(color_key, 'B4C6E7'))
        cell = ws.cell(row=header_row, column=idx, value=label)
        cell.font = header_font
        cell.fill = fill
        cell.alignment = align_center
        cell.border = border
        ws.column_dimensions[get_column_letter(idx)].width = COLUMN_WIDTHS.get(key, 11)

    ws.row_dimensions[header_row].height = 36
    ws.freeze_panes = ws.cell(row=data_start, column=1).coordinate

    totals = {key: 0.0 for key in MONEY_SUM_KEYS}

    for i, (run, line) in enumerate(line_pairs):
        r = data_start + i
        for col_idx, (key, _label, _color, col_type) in enumerate(PAYROLL_EXPORT_COLUMNS, start=1):
            raw = get_cell_value(line, run, key)
            if col_type == 'text':
                val = raw if raw not in (None, '') else None
            elif col_type == 'days':
                val = float(raw) if raw not in (None, '') else None
            else:
                val = _money(raw) if raw not in (None, '') else None
                if val is not None:
                    totals[key] += val

            cell = ws.cell(row=r, column=col_idx, value=val)
            cell.font = data_font
            cell.border = border
            if col_type == 'text':
                cell.alignment = align_right if key in ('employee_name', 'bank', 'company', 'branch') else align_center
            else:
                cell.alignment = align_center
            if col_type == 'money':
                cell.number_format = '#,##0.00'
            elif col_type == 'days':
                cell.number_format = '0.0'

        ws.row_dimensions[r].height = ROW_HEIGHT

    if line_pairs:
        footer_row = data_start + len(line_pairs)
        ws.row_dimensions[footer_row].height = ROW_HEIGHT
        for col_idx, (key, _label, _color, col_type) in enumerate(PAYROLL_EXPORT_COLUMNS, start=1):
            cell = ws.cell(row=footer_row, column=col_idx)
            cell.font = total_font
            cell.border = border
            cell.alignment = align_center
            if key == 'employee_name':
                cell.value = 'الإجمالي'
                cell.alignment = align_right
            elif col_type == 'money' and key in totals:
                cell.value = totals[key]
                cell.number_format = '#,##0.00'

    ws.print_options.horizontalCentered = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.oddHeader.center.text = meta_note


def _payroll_line_pairs_for_runs(runs):
    if not runs:
        return []
    run_ids = [run.id for run in runs]
    lines = payroll_lines_select_related(
        PayrollLine.objects.filter(run_id__in=run_ids),
    ).select_related('run', 'run__branch', 'run__sponsorship').order_by(
        'run__branch__name', 'employee__name',
    )
    return [(line.run, line) for line in lines]


def build_payroll_run_workbook(run):
    """يُنشئ Workbook بتنسيق كشف الرواتب (ترويسة ملوّنة + صفوف الموظفين)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = 'كشف الرواتب'[:31]
    ws.sheet_view.rightToLeft = True

    line_pairs = [(run, line) for line in payroll_lines_select_related(run.lines).order_by('employee__name')]
    meta_note = (
        f'{run.branch.name if run.branch_id else ""} — {run.period_label} — '
        f'تصدير {timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")}'
    )
    _write_payroll_sheet(ws, line_pairs, meta_note=meta_note)
    return wb


def build_payroll_runs_workbook(runs):
    """Workbook موحّد لعدة مسيرات (جدول واحد لكل الفروع المختارة)."""
    from openpyxl import Workbook

    runs = list(runs)
    if not runs:
        raise ValueError('لا توجد مسيرات للتصدير.')

    wb = Workbook()
    ws = wb.active
    ws.title = 'كشف الرواتب'[:31]
    ws.sheet_view.rightToLeft = True

    first = runs[0]
    branch_names = ', '.join(
        r.branch.name for r in runs if r.branch_id
    )[:120]
    meta_note = (
        f'{branch_names or "مسير موحّد"} — {first.period_label} — '
        f'تصدير {timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")}'
    )
    _write_payroll_sheet(ws, _payroll_line_pairs_for_runs(runs), meta_note=meta_note)
    return wb


@dataclass
class DetailedPayrollExportRow:
    alloc_line: object
    payroll_line: object


def detailed_allocation_lines_for_run(run):
    return run.allocation_lines.select_related(
        'employee',
        'employee__branch',
        'employee__branch__company',
        'employee__bank',
        'employee__sponsorship',
        'branch',
        'from_branch',
    ).order_by(
        'employee__name',
        'bears_salary',
        'days_in_branch',
        'transfer_date',
        'id',
    )


def _payroll_line_for_allocation(alloc_line, run, *, cache: dict):
    emp_id = alloc_line.employee_id
    if emp_id not in cache:
        source = lookup_source_payroll_line(alloc_line, run)
        cache[emp_id] = source or build_ephemeral_payroll_line(alloc_line.employee, run)
    return cache[emp_id]


def detailed_payroll_export_pairs(run):
    """صف لكل سطر توزيع فرع — بأعمدة كشف الرواتب."""
    cache = {}
    pairs = []
    for alloc_line in detailed_allocation_lines_for_run(run):
        payroll_line = _payroll_line_for_allocation(alloc_line, run, cache=cache)
        export_row = DetailedPayrollExportRow(
            alloc_line=alloc_line,
            payroll_line=payroll_line,
        )
        pairs.append((run, export_row))
    return pairs


def _resolve_detailed_export_row(export_row: DetailedPayrollExportRow, run, key: str):
    return resolve_detailed_allocation_cell_value(
        export_row.alloc_line,
        run,
        key,
        export_row.payroll_line,
    )


def build_payroll_detailed_run_workbook(run):
    """Workbook تفصيلي بأعمدة كشف الرواتب — صف لكل فرع في توزيع النقل."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = 'كشف الرواتب'[:31]
    ws.sheet_view.rightToLeft = True

    company_name = run.company.name if run.company_id else 'شركة'
    meta_note = (
        f'{company_name} — {run.period_label} — مسير تفصيلي — '
        f'تصدير {timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")}'
    )
    _write_payroll_sheet(
        ws,
        detailed_payroll_export_pairs(run),
        meta_note=meta_note,
        resolve_value=_resolve_detailed_export_row,
    )
    return wb


def build_payroll_detailed_runs_workbook(runs):
    """Workbook تفصيلي موحّد لعدة مسيرات تفصيلية (ورقة واحدة لكل الشركات المختارة)."""
    from openpyxl import Workbook

    runs = list(runs)
    if not runs:
        raise ValueError('لا توجد مسيرات تفصيلية للتصدير.')

    wb = Workbook()
    ws = wb.active
    ws.title = 'كشف الرواتب'[:31]
    ws.sheet_view.rightToLeft = True

    pairs = []
    for run in runs:
        pairs.extend(detailed_payroll_export_pairs(run))
    companies = ', '.join(dict.fromkeys(r.company.name for r in runs if r.company_id))[:120]
    meta_note = (
        f'{companies or "مسير تفصيلي"} — {runs[0].period_label} — مسير تفصيلي — '
        f'تصدير {timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")}'
    )
    _write_payroll_sheet(ws, pairs, meta_note=meta_note, resolve_value=_resolve_detailed_export_row)
    return wb


def payroll_detailed_runs_excel_filename(*, year: int, month: int, salary_mode: str) -> str:
    return f'payroll_detailed_{year}_{month:02d}_{salary_mode}.xlsx'


# ══════════════════════════════════════════════════════════════════════════════
# تصدير شامل متعدد الأوراق: كشف + تحليل الفروع + الشركات + تحويل + نقدي + تفصيلي
# ══════════════════════════════════════════════════════════════════════════════
_SUMMARY_COLUMNS = [
    ('employee_number', 'الرقم الوظيفي', 12),
    ('employee_name', 'الاسم', 26),
    ('branch', 'الفرع', 16),
    ('salary_gross', 'إجمالي الراتب', 14),
    ('total_earnings', 'إجمالي المستحق', 14),
    ('total_deductions', 'إجمالي الخصومات', 14),
    ('net_salary', 'الصافي', 14),
]


def _sheet_styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    thin = Side(border_style='thin', color='94A3B8')
    return {
        'border': Border(left=thin, right=thin, top=thin, bottom=thin),
        'center': Alignment(horizontal='center', vertical='center', wrap_text=True),
        'right': Alignment(horizontal='right', vertical='center'),
        'head_font': Font(name='Arial', size=10, bold=True, color='FFFFFF'),
        'head_fill': PatternFill('solid', fgColor='1E40AF'),
        'title_font': Font(name='Arial', size=12, bold=True, color='1E3A8A'),
        'title_fill': PatternFill('solid', fgColor='DBEAFE'),
        'data_font': Font(name='Arial', size=10),
        'total_font': Font(name='Arial', size=10, bold=True),
        'total_fill': PatternFill('solid', fgColor='F1F5F9'),
    }


def _write_table(ws, start_row: int, headers: list[str], rows: list[list], *,
                 title: str | None = None, money_cols: set[int] = frozenset(),
                 total_row: list | None = None) -> int:
    """يكتب جدولاً منسّقاً بدءاً من start_row ويُرجع أول صف فارغ بعده."""
    st = _sheet_styles()
    r = start_row
    ncols = len(headers)
    if title:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        cell = ws.cell(row=r, column=1, value=title)
        cell.font, cell.fill, cell.alignment = st['title_font'], st['title_fill'], st['right']
        ws.row_dimensions[r].height = 22
        r += 1
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = (
            st['head_font'], st['head_fill'], st['center'], st['border'],
        )
    ws.row_dimensions[r].height = 28
    r += 1
    for row in rows:
        for c, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font, cell.border = st['data_font'], st['border']
            cell.alignment = st['center'] if c in money_cols else st['right']
            if c in money_cols:
                cell.number_format = '#,##0.00'
        r += 1
    if total_row is not None:
        for c, v in enumerate(total_row, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font, cell.fill, cell.border = st['total_font'], st['total_fill'], st['border']
            cell.alignment = st['center'] if c in money_cols else st['right']
            if c in money_cols:
                cell.number_format = '#,##0.00'
        r += 1
    return r


def _new_sheet(wb, title: str):
    ws = wb.create_sheet(title=title[:31])
    ws.sheet_view.rightToLeft = True
    return ws


def _line_branch(line, run) -> str:
    return resolve_cell_value(line, run, 'branch') or '—'


def _line_company(line, run) -> str:
    if run.salary_mode == 'cash':
        return 'نقدي — بدون كفالة'
    emp = line.employee
    if emp.sponsorship_id and getattr(emp, 'sponsorship', None):
        return (emp.sponsorship.company_name or '').strip() or '—'
    return resolve_cell_value(line, run, 'company') or '—'


def _money(v) -> float:
    return float(v or 0)


def _write_analysis_sheet(ws, pairs) -> None:
    """التحليل: إجماليات حسب الفرع + حسب نوع الصرف."""
    by_branch: dict[str, dict] = {}
    by_mode = {'transfer': {'n': 0, 'gross': 0.0, 'ded': 0.0, 'net': 0.0},
               'cash': {'n': 0, 'gross': 0.0, 'ded': 0.0, 'net': 0.0}}
    for run, line in pairs:
        b = by_branch.setdefault(_line_branch(line, run), {
            'n': 0, 'gross': 0.0, 'earn': 0.0, 'ded': 0.0, 'net': 0.0, 'transfer': 0.0, 'cash': 0.0,
        })
        b['n'] += 1
        b['gross'] += _money(line.gross_salary)
        b['earn'] += _money(line.total_earnings)
        b['ded'] += _money(line.total_deductions)
        b['net'] += _money(line.net_salary)
        b[run.salary_mode] += _money(line.net_salary)
        m = by_mode[run.salary_mode]
        m['n'] += 1
        m['gross'] += _money(line.gross_salary)
        m['ded'] += _money(line.total_deductions)
        m['net'] += _money(line.net_salary)

    rows = [
        [name, v['n'], v['gross'], v['earn'], v['ded'], v['net'], v['transfer'], v['cash']]
        for name, v in sorted(by_branch.items(), key=lambda kv: -kv[1]['net'])
    ]
    tot = [sum(r[i] for r in rows) for i in range(1, 8)]
    r = _write_table(
        ws, 1,
        ['الفرع', 'عدد الموظفين', 'إجمالي الرواتب', 'إجمالي المستحق', 'إجمالي الخصومات',
         'الصافي', 'منه تحويل', 'منه نقدي'],
        rows, title='تحليل المسير حسب الفرع', money_cols={3, 4, 5, 6, 7, 8},
        total_row=['الإجمالي', *tot],
    )
    mode_rows = [
        [label, by_mode[k]['n'], by_mode[k]['gross'], by_mode[k]['ded'], by_mode[k]['net']]
        for k, label in (('transfer', 'تحويل بنكي'), ('cash', 'نقدي'))
    ]
    _write_table(
        ws, r + 1,
        ['نوع الصرف', 'عدد الموظفين', 'إجمالي الرواتب', 'إجمالي الخصومات', 'الصافي'],
        mode_rows, title='حسب نوع الصرف', money_cols={3, 4, 5},
        total_row=['الإجمالي', *[sum(x[i] for x in mode_rows) for i in range(1, 5)]],
    )
    from openpyxl.utils import get_column_letter
    for c, w in enumerate([22, 13, 15, 15, 15, 15, 14, 14], start=1):
        ws.column_dimensions[get_column_letter(c)].width = w


def _summary_row(line, run) -> list:
    return [
        _money(resolve_cell_value(line, run, k)) if k in MONEY_SUM_KEYS else (
            resolve_cell_value(line, run, k) or '—'
        )
        for k, _label, _w in _SUMMARY_COLUMNS
    ]


def _write_companies_sheet(ws, pairs) -> None:
    """جدول مستقل لكل شركة كفالة (والنقدي في جدول أخير)."""
    groups: dict[str, list] = {}
    for run, line in pairs:
        groups.setdefault(_line_company(line, run), []).append((run, line))
    headers = [label for _k, label, _w in _SUMMARY_COLUMNS]
    money_cols = {i for i, (k, _l, _w) in enumerate(_SUMMARY_COLUMNS, start=1) if k in MONEY_SUM_KEYS}
    ordered = sorted(groups, key=lambda name: (name.startswith('نقدي'), name))
    r = 1
    for name in ordered:
        items = sorted(groups[name], key=lambda p: (_line_branch(p[1], p[0]), p[1].employee.name))
        rows = [_summary_row(line, run) for run, line in items]
        total = ['الإجمالي', f'{len(rows)} موظف', '']
        total += [sum(row[i - 1] for row in rows) for i in range(4, len(headers) + 1)]
        net = sum(_money(line.net_salary) for _run, line in items)
        r = _write_table(
            ws, r, headers, rows,
            title=f'{name} — {len(rows)} موظف — صافي {net:,.2f}',
            money_cols=money_cols, total_row=total,
        ) + 1
    from openpyxl.utils import get_column_letter
    for c, (_k, _l, w) in enumerate(_SUMMARY_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(c)].width = w


def build_payroll_full_workbook(*, transfer_runs, cash_runs, detailed_runs, period_label: str):
    """
    ملف واحد بعدة أوراق:
    كشف الرواتب (الكل) · التحليل (الفروع) · حسب الشركات · التحويل · النقدي · التفصيلي.
    """
    from openpyxl import Workbook

    transfer_runs, cash_runs = list(transfer_runs), list(cash_runs)
    if not transfer_runs and not cash_runs:
        raise ValueError('لا توجد مسيرات للتصدير.')
    stamp = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')
    transfer_pairs = _payroll_line_pairs_for_runs(transfer_runs)
    cash_pairs = _payroll_line_pairs_for_runs(cash_runs)
    all_pairs = transfer_pairs + cash_pairs

    wb = Workbook()
    ws = wb.active
    ws.title = 'كشف الرواتب'
    ws.sheet_view.rightToLeft = True
    _write_payroll_sheet(ws, all_pairs, meta_note=f'كشف الرواتب — {period_label} — تصدير {stamp}')

    _write_analysis_sheet(_new_sheet(wb, 'التحليل'), all_pairs)
    _write_companies_sheet(_new_sheet(wb, 'حسب الشركات'), all_pairs)

    _write_payroll_sheet(_new_sheet(wb, 'التحويل'), transfer_pairs,
                         meta_note=f'موظفو التحويل — {period_label}')
    _write_payroll_sheet(_new_sheet(wb, 'النقدي'), cash_pairs,
                         meta_note=f'موظفو النقدي — {period_label}')

    detailed_pairs = []
    for run in detailed_runs or []:
        detailed_pairs.extend(detailed_payroll_export_pairs(run))
    ws_d = _new_sheet(wb, 'التفصيلي')
    if detailed_pairs:
        _write_payroll_sheet(ws_d, detailed_pairs, meta_note=f'المسير التفصيلي — {period_label}',
                             resolve_value=_resolve_detailed_export_row)
    else:
        ws_d.cell(row=1, column=1, value='لا يوجد مسير تفصيلي (نقل موظفين بين الفروع) لهذه الفترة.')
    return wb


def payroll_full_excel_filename(*, year: int, month: int) -> str:
    return f'payroll_{year}_{month:02d}_full.xlsx'


def payroll_run_excel_filename(run) -> str:
    branch = run.branch_id or 'run'
    return f'payroll_{branch}_{run.period_year}_{run.period_month:02d}.xlsx'


def payroll_detailed_run_excel_filename(run) -> str:
    company = (run.company.name if run.company_id else 'detailed').replace(' ', '_')[:40]
    return f'payroll_detailed_{company}_{run.period_year}_{run.period_month:02d}.xlsx'


def payroll_runs_excel_filename(*, year: int, month: int, salary_mode: str) -> str:
    return f'payroll_{year}_{month:02d}_{salary_mode}.xlsx'


def workbook_to_response(wb, filename: str):
    from django.http import HttpResponse

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
