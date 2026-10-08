"""PDF رسمي موحّد لكل التقارير — ترويسة المنشأة، بيانات الإصدار، جدول، توقيعات، ترقيم صفحات."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from apps.core.services.operations_report_pdf import _font_path, _pdf_text

_MARGIN = 10
_ROW_H = 6.2
_HEAD_H = 7.5
_MAX_PORTRAIT_COLS = 6
_NAVY = (30, 64, 175)
_SLATE = (71, 85, 105)
_LINE = (203, 213, 225)
_ZEBRA = (248, 250, 252)


@dataclass
class ReportPdfMeta:
    title: str
    company_name: str = 'نظام الموارد البشرية'
    period: str = ''
    scope: str = ''
    prepared_by: str = ''
    reference: str = ''
    issued_at: datetime = field(default_factory=datetime.now)
    note: str = ''
    total_rows: int | None = None


_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')


def _latin_fallback_font() -> Path | None:
    """خط Noto العربي لا يحتوي الحروف اللاتينية و«/» و«—»؛ نستعير DejaVu المرفق مع مكتبة barcode."""
    try:
        import barcode
        path = Path(barcode.__file__).parent / 'fonts' / 'DejaVuSansMono.ttf'
        return path if path.is_file() else None
    except Exception:  # pragma: no cover - اختياري
        return None


_NOTO_SAFE_RE = re.compile(r'^[0-9:.,\-+% ()]*$')


def _font_for(pdf: FPDF, text: str, size: float) -> None:
    """يبدّل لخط لاتيني فقط للنص الذي يحوي حروفاً لاتينية أو رموزاً لا يدعمها Noto (/ # —)."""
    raw = str(text or '')
    needs_latin = (
        getattr(pdf, 'has_latin_font', False)
        and not _ARABIC_RE.search(raw)
        and not _NOTO_SAFE_RE.match(raw)
    )
    pdf.set_font('LatinFont' if needs_latin else 'NotoArabic', '', size)


def _draw_segments(pdf: FPDF, x_right: float, y: float, h: float, segments: list[str], gap: float = 1.6) -> float:
    """يرسم أجزاءً نصية من اليمين لليسار كل جزء بخلية مستقلة، فلا يخلط الاتجاه بين العربي والأرقام."""
    x = x_right
    for seg in segments:
        if seg is None or seg == '':
            continue
        text = _pdf_text(seg) if _ARABIC_RE.search(str(seg)) else str(seg)
        _font_for(pdf, str(seg), pdf.font_size_pt)
        w = pdf.get_string_width(text) + 0.4
        x -= w
        pdf.set_xy(x, y)
        pdf.cell(w, h, text, align='L')
        x -= gap
    return x


class _OfficialPDF(FPDF):
    def __init__(self, meta: ReportPdfMeta, landscape: bool):
        super().__init__(orientation='L' if landscape else 'P', unit='mm', format='A4')
        self.meta = meta
        self.set_auto_page_break(auto=True, margin=22)
        self.add_font('NotoArabic', '', str(_font_path()))
        self.has_latin_font = False
        fallback = _latin_fallback_font()
        if fallback:
            self.add_font('LatinFont', '', str(fallback))
            self.has_latin_font = True
        self.total_pages: int | None = None
        self.alias_nb_pages()
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)

    @property
    def body_w(self) -> float:
        return self.w - 2 * _MARGIN

    def header(self):
        if self.page_no() > 1:
            # ترويسة مختصرة للصفحات التالية
            self.set_font('NotoArabic', '', 9)
            self.set_text_color(*_SLATE)
            _draw_segments(self, self.w - _MARGIN, 8, 6, [self.meta.title, '|', self.meta.reference])
            self.set_draw_color(*_LINE)
            self.line(_MARGIN, 14.5, self.w - _MARGIN, 14.5)
            self.set_y(18)
            return
        self.set_fill_color(*_NAVY)
        self.rect(0, 0, self.w, 4, style='F')
        self.set_y(9)
        self.set_text_color(15, 23, 42)
        self.set_font('NotoArabic', '', 11)
        self.cell(self.body_w, 6, _pdf_text(self.meta.company_name), align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_font('NotoArabic', '', 18)
        self.set_text_color(*_NAVY)
        self.cell(self.body_w, 11, _pdf_text(self.meta.title), align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*_NAVY)
        self.set_line_width(0.5)
        self.line(_MARGIN, self.get_y() + 1, self.w - _MARGIN, self.get_y() + 1)
        self.set_line_width(0.2)
        self.set_y(self.get_y() + 4)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(*_LINE)
        self.line(_MARGIN, self.get_y(), self.w - _MARGIN, self.get_y())
        self.set_font('NotoArabic', '', 8)
        self.set_text_color(100, 116, 139)
        y = self.get_y() + 1.5
        # يمين: «صفحة 1 من 3» — يسار: تاريخ الإصدار
        total = str(self.total_pages) if self.total_pages else '{nb}'
        _draw_segments(self, self.w - _MARGIN, y, 5, ['صفحة', str(self.page_no()), 'من', total])
        self.set_font('NotoArabic', '', 8)
        self.set_xy(_MARGIN, y)
        self.cell(40, 5, self.meta.issued_at.strftime('%Y-%m-%d %H:%M'), align='L')


def _fit(pdf: FPDF, text: str, width: float) -> str:
    """يقتطع النص ليلائم عرض الخلية (بعد التشكيل العربي)."""
    raw_full = str(text or '-').strip() or '-'
    _font_for(pdf, raw_full, pdf.font_size_pt)
    shaped = _pdf_text(raw_full)
    if pdf.get_string_width(shaped) <= width - 1.6:
        return shaped
    raw = raw_full
    while len(raw) > 1:
        raw = raw[:-1]
        candidate = _pdf_text(raw + '...')
        if pdf.get_string_width(candidate) <= width - 1.6:
            return candidate
    return _pdf_text('...')


def _column_widths(pdf: FPDF, columns: list[str], rows: list[list], total: float, num_w: float) -> list[float]:
    """عرض كل عمود بنسبة أطول نص فيه (بحد أدنى وأقصى) ثم تطبيع للعرض المتاح."""
    avail = total - num_w
    weights = []
    sample = rows[:200]
    for idx, col in enumerate(columns):
        longest = len(str(col))
        for r in sample:
            if idx < len(r):
                longest = max(longest, len(str(r[idx] if r[idx] is not None else '')))
        header_need = -(-len(str(col)) // 2) + 2  # العنوان قد يلتف على سطرين
        data_longest = max([len(str(r[idx] if r[idx] is not None else '')) for r in sample if idx < len(r)] or [0])
        weights.append(min(max(data_longest, header_need, 5), 34))
    scale = avail / sum(weights)
    return [w * scale for w in weights]


def _meta_block(pdf: _OfficialPDF) -> None:
    m = pdf.meta
    items: list[tuple[str, list[str]]] = []
    if m.period:
        items.append(('الفترة', m.period.split('|')))
    if m.scope:
        items.append(('النطاق', [m.scope]))
    if m.total_rows is not None:
        items.append(('عدد السجلات', [str(m.total_rows)]))
    if m.prepared_by:
        items.append(('أعدّه', [m.prepared_by]))
    if m.reference:
        items.append(('الرقم المرجعي', [m.reference]))
    if not items:
        return
    per_row = 3 if pdf.w > 250 else 2
    cell_w = pdf.body_w / per_row
    pdf.set_font('NotoArabic', '', 9)
    for i in range(0, len(items), per_row):
        y = pdf.get_y()
        for pos, (label, value_parts) in enumerate(items[i:i + per_row]):
            x_right = pdf.w - _MARGIN - pos * cell_w
            pdf.set_text_color(*_SLATE)
            x = _draw_segments(pdf, x_right, y, 5.5, [label + ':'], gap=1.2)
            pdf.set_text_color(15, 23, 42)
            _draw_segments(pdf, x, y, 5.5, value_parts)
        pdf.set_y(y + 6.2)
    if m.note:
        pdf.set_font('NotoArabic', '', 8)
        pdf.set_text_color(*_SLATE)
        pdf.set_x(_MARGIN)
        pdf.cell(pdf.body_w, 5, _fit(pdf, m.note, pdf.body_w), align='R', new_x='LMARGIN', new_y='NEXT')
    pdf.set_y(pdf.get_y() + 2)


def _table(pdf: _OfficialPDF, columns: list[str], rows: list[list]) -> None:
    num_w = 9.0
    widths = _column_widths(pdf, columns, rows, pdf.body_w, num_w)

    head_h = 10.0

    def draw_head_cell(x: float, y: float, w: float, text: str) -> None:
        pdf.set_fill_color(*_NAVY)
        pdf.set_draw_color(*_NAVY)
        pdf.rect(x, y, w, head_h, style='DF')
        pdf.set_text_color(255, 255, 255)
        raw = str(text or '')
        lines = [raw]
        _font_for(pdf, raw, 8)
        if pdf.get_string_width(_pdf_text(raw)) > w - 1.6 and ' ' in raw:
            words = raw.split()
            best = min(range(1, len(words)), key=lambda k: abs(len(' '.join(words[:k])) - len(' '.join(words[k:]))))
            lines = [' '.join(words[:best]), ' '.join(words[best:])]
        line_h = head_h / (len(lines) + 0.4)
        top = y + (head_h - line_h * len(lines)) / 2
        for i, line in enumerate(lines):
            pdf.set_xy(x, top + i * line_h)
            pdf.cell(w, line_h, _fit(pdf, line, w), align='C')

    def draw_head():
        y = pdf.get_y()
        x = pdf.w - _MARGIN - num_w
        draw_head_cell(x, y, num_w, '#')
        for col, w in zip(columns, widths):
            x -= w
            draw_head_cell(x, y, w, col)
        pdf.set_y(y + head_h)

    draw_head()
    pdf.set_font('NotoArabic', '', 8)
    pdf.set_draw_color(*_LINE)
    for n, row in enumerate(rows, 1):
        if pdf.get_y() + _ROW_H > pdf.h - 24:
            pdf.add_page()
            draw_head()
            pdf.set_font('NotoArabic', '', 8)
            pdf.set_draw_color(*_LINE)
        y = pdf.get_y()
        fill = n % 2 == 0
        pdf.set_fill_color(*_ZEBRA)
        pdf.set_text_color(15, 23, 42)
        x = pdf.w - _MARGIN - num_w
        pdf.set_xy(x, y)
        pdf.set_font('NotoArabic', '', 8)
        pdf.cell(num_w, _ROW_H, str(n), border=1, align='C', fill=fill)
        for idx, w in enumerate(widths):
            x -= w
            val = row[idx] if idx < len(row) else ''
            pdf.set_xy(x, y)
            pdf.cell(w, _ROW_H, _fit(pdf, '' if val is None else val, w), border=1, align='R', fill=fill)
            pdf.set_font('NotoArabic', '', 8)
        pdf.set_y(y + _ROW_H)


def _signatures(pdf: _OfficialPDF) -> None:
    if pdf.get_y() + 26 > pdf.h - 18:
        pdf.add_page()
    pdf.set_y(pdf.get_y() + 8)
    pdf.set_font('NotoArabic', '', 9)
    pdf.set_text_color(*_SLATE)
    pdf.set_draw_color(*_SLATE)
    labels = ['أعدّه', 'راجعه', 'اعتمده']
    slot = pdf.body_w / len(labels)
    y = pdf.get_y()
    for i, label in enumerate(labels):
        x_right = pdf.w - _MARGIN - i * slot
        pdf.set_xy(x_right - slot, y)
        pdf.cell(slot, 5, _pdf_text(label), align='C')
        pdf.line(x_right - slot + 12, y + 16, x_right - 12, y + 16)
        pdf.set_xy(x_right - slot, y + 17)
        pdf.set_font('NotoArabic', '', 7.5)
        pdf.cell(slot, 4, _pdf_text('الاسم والتوقيع والتاريخ'), align='C')
        pdf.set_font('NotoArabic', '', 9)


def _render(meta: ReportPdfMeta, columns: list[str], rows: list[list], total_pages: int | None) -> _OfficialPDF:
    landscape = len(columns) > _MAX_PORTRAIT_COLS
    pdf = _OfficialPDF(meta, landscape)
    pdf.total_pages = total_pages
    pdf.add_page()
    _meta_block(pdf)
    if rows and columns:
        _table(pdf, columns, rows)
    else:
        pdf.set_font('NotoArabic', '', 11)
        pdf.set_text_color(*_SLATE)
        pdf.cell(pdf.body_w, 20, _pdf_text('لا توجد بيانات ضمن الشروط المحددة'), align='C')
        pdf.ln(22)
    _signatures(pdf)
    return pdf


def build_report_pdf(meta: ReportPdfMeta, columns: list[str], rows: list[list]) -> bytes:
    """يُنشئ PDF رسمياً: A4 أفقي إن زادت الأعمدة عن 6، وإلا عمودي. يُرسم مرتين ليظهر عدد الصفحات الكلي."""
    first = _render(meta, columns, rows, None)
    final = _render(meta, columns, rows, first.page_no())
    return bytes(final.output())
