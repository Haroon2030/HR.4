"""توليد PDF لتقرير العمليات اليومي — تصميم رسمي منظم."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from django.conf import settings
from fpdf import FPDF

from apps.core.services.operations_report_data import (
    OperationsReportBundle,
    OperationsReportRow,
    OperationsReportSection,
)


def _shape_ar(text: str) -> str:
    raw = str(text or '-').strip() or '-'
    return get_display(arabic_reshaper.reshape(raw))


def _pdf_text(text: str) -> str:
    """نص عربي مُشكّل أو لاتيني/أرقام كما هي."""
    raw = str(text or '-').strip() or '-'
    ascii_chars = sum(1 for c in raw if ord(c) < 128)
    if ascii_chars >= len(raw) * 0.6:
        return raw
    return _shape_ar(raw)


def _font_path() -> Path:
    candidates = [
        Path(settings.BASE_DIR) / 'static' / 'fonts' / 'noto' / 'NotoSansArabic-Regular.ttf',
        Path(settings.BASE_DIR) / 'staticfiles' / 'fonts' / 'noto' / 'NotoSansArabic-Regular.ttf',
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError('NotoSansArabic-Regular.ttf غير موجود — أعد collectstatic أو أضف الخط.')


class _ArabicPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='L', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=12)
        self.add_font('NotoArabic', '', str(_font_path()))
        self.set_font('NotoArabic', '', 10)

    def footer(self):
        self.set_y(-10)
        self.set_font('NotoArabic', '', 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 6, _pdf_text(f'صفحة {self.page_no()}'), align='C')


class _ReportPDF(_ArabicPDF):
    MARGIN = 10
    COL_W = (8, 22, 38, 32, 78, 28, 32)  # #, ref, employee, branch, details, amount, date
    TABLE_W = sum(COL_W)

    def _draw_header(self, report_date: date, bundle: OperationsReportBundle) -> None:
        self.set_fill_color(15, 23, 42)
        self.rect(self.MARGIN, self.MARGIN, self.w - 2 * self.MARGIN, 22, style='F')
        self.set_xy(self.MARGIN + 4, self.MARGIN + 4)
        self.set_font('NotoArabic', '', 18)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, _shape_ar('تقرير العمليات اليومي'), ln=True)
        self.set_x(self.MARGIN + 4)
        self.set_font('NotoArabic', '', 10)
        self.set_text_color(203, 213, 225)
        completed_total = sum(len(s.completed_rows) for s in bundle.sections)
        pending_total = sum(len(s.pending_rows) for s in bundle.sections)
        meta = (
            f'تاريخ التقرير: {report_date.isoformat()}   '
            f'عمليات اليوم: {completed_total}   '
            f'معلّق: {pending_total}'
        )
        self.cell(0, 6, _shape_ar(meta), ln=True)
        self.set_text_color(0, 0, 0)
        self.set_y(self.MARGIN + 26)

    def _draw_summary(self, bundle: OperationsReportBundle) -> None:
        self.set_font('NotoArabic', '', 9)
        x = self.MARGIN
        y = self.get_y()
        box_h = 14
        gap = 3
        boxes = [(s.title, len(s.completed_rows), len(s.pending_rows), s.accent_rgb) for s in bundle.sections]
        count = len(boxes)
        if not count:
            return
        box_w = min(42, (self.TABLE_W - gap * (count - 1)) / count)
        for title, done, pending, rgb in boxes:
            self.set_fill_color(*rgb)
            self.rect(x, y, box_w, 4, style='F')
            self.set_fill_color(248, 250, 252)
            self.rect(x, y + 4, box_w, box_h - 4, style='F')
            self.set_xy(x + 2, y + 5)
            self.set_text_color(30, 41, 59)
            self.cell(box_w - 4, 4, _shape_ar(title), ln=True)
            self.set_x(x + 2)
            self.set_font('NotoArabic', '', 8)
            self.set_text_color(71, 85, 105)
            self.cell(box_w - 4, 4, _shape_ar(f'اليوم {done}   معلّق {pending}'), ln=False)
            self.set_font('NotoArabic', '', 9)
            x += box_w + gap
        self.set_text_color(0, 0, 0)
        self.set_y(y + box_h + 4)

    def _draw_table_header(self) -> None:
        headers = ('#', 'المرجع', 'الموظف', 'الفرع', 'التفاصيل', 'المبلغ', 'التاريخ')
        self.set_font('NotoArabic', '', 8)
        self.set_fill_color(226, 232, 240)
        self.set_text_color(30, 41, 59)
        x0 = self.MARGIN
        for header, width in zip(headers, self.COL_W):
            self.set_x(x0)
            self.cell(width, 7, _shape_ar(header), border=1, fill=True)
            x0 += width
        self.ln()
        self.set_text_color(0, 0, 0)

    def _truncate(self, text: str, max_len: int) -> str:
        t = str(text or '—')
        return t if len(t) <= max_len else t[: max_len - 1] + '…'

    def _draw_rows(self, rows: list[OperationsReportRow]) -> None:
        self.set_font('NotoArabic', '', 8)
        for idx, row in enumerate(rows, start=1):
            if self.get_y() > self.h - 20:
                self.add_page()
                self._draw_table_header()
            fill = idx % 2 == 0
            if fill:
                self.set_fill_color(248, 250, 252)
            values = (
                str(idx),
                row.ref,
                self._truncate(row.employee_name, 22),
                self._truncate(row.branch_name, 18),
                self._truncate(row.details, 48),
                row.amount_label,
                row.date_label,
            )
            x0 = self.MARGIN
            for value, width in zip(values, self.COL_W):
                self.set_x(x0)
                self.cell(width, 6, _pdf_text(value), border=1, fill=fill)
                x0 += width
            self.ln()

    def _draw_section(
        self,
        section: OperationsReportSection,
        *,
        mode: str,
        start_index: int = 1,
    ) -> int:
        rows = section.completed_rows if mode == 'completed' else section.pending_rows
        if not rows:
            return start_index

        if self.get_y() > self.h - 35:
            self.add_page()

        r, g, b = section.accent_rgb
        self.set_fill_color(r, g, b)
        title = section.title
        if mode == 'pending':
            title = f'{section.title} — معلّق ({len(rows)})'
        else:
            title = f'{section.title} — اليوم ({len(rows)})'
        self.set_font('NotoArabic', '', 11)
        self.set_text_color(255, 255, 255)
        self.cell(self.TABLE_W, 8, _shape_ar(title), border=0, fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(1)
        self._draw_table_header()
        self._draw_rows(rows)
        self.ln(3)
        return start_index + len(rows)


def build_operations_report_pdf(
    *,
    report_date: date,
    bundle: OperationsReportBundle | None = None,
    pending_rows: list[OperationsReportRow] | None = None,
    completed_rows: list[OperationsReportRow] | None = None,
    include_pending: bool = True,
    include_completed: bool = True,
) -> bytes:
    if bundle is None:
        from apps.core.services.operations_report_data import collect_operations_report

        bundle = collect_operations_report(
            report_date=report_date,
            include_pending=include_pending,
            include_completed=include_completed,
        )

    pdf = _ReportPDF()
    pdf.add_page()
    pdf._draw_header(report_date, bundle)
    pdf._draw_summary(bundle)

    if include_completed:
        pdf.set_font('NotoArabic', '', 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 8, _shape_ar('عمليات اليوم — حسب القسم'), ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)
        for section in bundle.sections:
            pdf._draw_section(section, mode='completed')

    if include_pending:
        has_pending = any(s.pending_rows for s in bundle.sections)
        if has_pending:
            if pdf.get_y() > pdf.h - 40:
                pdf.add_page()
            pdf.set_font('NotoArabic', '', 12)
            pdf.set_text_color(180, 83, 9)
            pdf.cell(0, 8, _shape_ar('عمليات معلّقة — تحتاج متابعة'), ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            for section in bundle.sections:
                pdf._draw_section(section, mode='pending')

    out = pdf.output(dest='S')
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode('latin-1')
