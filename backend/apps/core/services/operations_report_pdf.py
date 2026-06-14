"""توليد PDF لتقرير العمليات (عربي RTL)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from django.conf import settings
from fpdf import FPDF

from apps.core.services.operations_report_data import OperationsReportRow


def _shape_ar(text: str) -> str:
    raw = str(text or '—').strip() or '—'
    return get_display(arabic_reshaper.reshape(raw))


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
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=14)
        self.add_font('NotoArabic', '', str(_font_path()))
        self.set_font('NotoArabic', '', 11)


def _draw_section(pdf: _ArabicPDF, title: str, rows: list[OperationsReportRow]) -> None:
    pdf.ln(4)
    pdf.set_font('NotoArabic', '', 13)
    pdf.cell(0, 8, _shape_ar(title), ln=True)
    pdf.set_font('NotoArabic', '', 9)

    if not rows:
        pdf.cell(0, 7, _shape_ar('لا توجد سجلات.'), ln=True)
        return

    col_w = (18, 34, 38, 30, 32, 38)
    headers = ('المرجع', 'نوع العملية', 'الموظف', 'الفرع', 'الحالة', 'التاريخ')
    pdf.set_fill_color(241, 245, 249)
    for header, width in zip(headers, col_w):
        pdf.cell(width, 7, _shape_ar(header), border=1, fill=True)
    pdf.ln()

    pdf.set_fill_color(255, 255, 255)
    for row in rows:
        values = (
            row.ref,
            row.action_label,
            row.employee_name,
            row.branch_name,
            row.status_label,
            row.date_label,
        )
        for value, width in zip(values, col_w):
            text = _shape_ar(value)
            if len(text) > 32:
                text = text[:31] + '…'
            pdf.cell(width, 7, text, border=1)
        pdf.ln()


def build_operations_report_pdf(
    *,
    report_date: date,
    pending_rows: list[OperationsReportRow],
    completed_rows: list[OperationsReportRow],
    include_pending: bool,
    include_completed: bool,
) -> bytes:
    pdf = _ArabicPDF()
    pdf.add_page()
    pdf.set_font('NotoArabic', '', 16)
    pdf.cell(0, 10, _shape_ar('تقرير العمليات'), ln=True, align='C')
    pdf.set_font('NotoArabic', '', 11)
    pdf.cell(0, 7, _shape_ar(f'تاريخ التقرير: {report_date.isoformat()}'), ln=True, align='C')
    pdf.ln(2)

    if include_pending:
        _draw_section(pdf, f'العمليات المعلّقة ({len(pending_rows)})', pending_rows)
    if include_completed:
        _draw_section(
            pdf,
            f'العمليات المُنجزة — {report_date.isoformat()} ({len(completed_rows)})',
            completed_rows,
        )

    out = pdf.output(dest='S')
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode('latin-1')
