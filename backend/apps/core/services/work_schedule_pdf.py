"""PDF رسمي لجدول دوام الموظف."""
from __future__ import annotations

from typing import Any

from django.utils import timezone
from fpdf import FPDF

from apps.core.services.operations_report_pdf import _font_path, _pdf_text, _shape_ar


class _WorkSchedulePDF(FPDF):
    MARGIN = 8
    COLS = 31

    def __init__(self):
        super().__init__(orientation='L', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=10)
        self.add_font('NotoArabic', '', str(_font_path()))
        self.set_font('NotoArabic', '', 10)
        self._col_w = (self.w - 2 * self.MARGIN) / self.COLS

    def footer(self):
        self.set_y(-9)
        self.set_font('NotoArabic', '', 7)
        self.set_text_color(100, 116, 139)
        self.cell(
            0,
            5,
            _pdf_text(f'صفحة {self.page_no()} — وثيقة رسمية — نظام الموارد البشرية'),
            align='C',
        )
        self.set_text_color(0, 0, 0)

    def _draw_doc_header(self, employee) -> None:
        self.set_fill_color(15, 118, 110)
        self.rect(self.MARGIN, self.MARGIN, self.w - 2 * self.MARGIN, 20, style='F')
        self.set_xy(self.MARGIN + 4, self.MARGIN + 3)
        self.set_font('NotoArabic', '', 16)
        self.set_text_color(255, 255, 255)
        self.cell(0, 7, _shape_ar('جدول الدوام الشهري — وثيقة رسمية'), ln=True)
        self.set_x(self.MARGIN + 4)
        self.set_font('NotoArabic', '', 10)
        branch = getattr(getattr(employee, 'branch', None), 'name', '') or '—'
        emp_no = getattr(employee, 'employee_number', '') or '—'
        issued = timezone.localdate().isoformat()
        meta = f'الموظف: {employee.name}   |   الرقم الوظيفي: {emp_no}   |   الفرع: {branch}   |   الإصدار: {issued}'
        self.cell(0, 5, _shape_ar(meta), ln=True)
        self.set_text_color(0, 0, 0)
        self.set_y(self.MARGIN + 24)

    def _draw_month_title(self, box: dict[str, Any]) -> None:
        self.set_fill_color(240, 253, 250)
        self.set_draw_color(203, 213, 225)
        self.rect(self.MARGIN, self.get_y(), self.w - 2 * self.MARGIN, 10, style='FD')
        self.set_xy(self.MARGIN + 3, self.get_y() + 2)
        self.set_font('NotoArabic', '', 11)
        self.set_text_color(15, 23, 42)
        title = (
            f'جدول عمل شهر {box["month_name"]} {box["year"]} — '
            f'{box["shift_title"]} — {box["days_count"]} يوم دوام'
        )
        self.cell(0, 6, _shape_ar(title), ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def _draw_weekday_cell(self, x: float, y: float, w: float, h: float, label: str, active: bool) -> None:
        if active:
            self.set_fill_color(31, 107, 128)
        else:
            self.set_fill_color(148, 163, 184)
        self.set_draw_color(203, 213, 225)
        self.rect(x, y, w, h, style='FD')
        if not label:
            return
        self.set_font('NotoArabic', '', 6)
        self.set_text_color(255, 255, 255)
        shaped = _shape_ar(label)
        cx = x + (w / 2)
        cy = y + (h / 2)
        with self.rotation(90, x=cx, y=cy):
            tw = self.get_string_width(shaped)
            self.set_xy(cx - (tw / 2), cy - 1.5)
            self.cell(tw, 3, shaped)
        self.set_text_color(0, 0, 0)

    def _draw_grid(self, box: dict[str, Any]) -> None:
        x0 = self.MARGIN
        y0 = self.get_y()
        row_wd = 14.0
        row_num = 6.0
        row_code = 7.0
        cw = self._col_w

        for idx, cell in enumerate(box['day_cells']):
            x = x0 + (idx * cw)
            self._draw_weekday_cell(
                x,
                y0,
                cw,
                row_wd,
                cell.get('weekday') or '—',
                bool(cell.get('active')),
            )

        y_num = y0 + row_wd
        self.set_font('NotoArabic', '', 7)
        for idx, cell in enumerate(box['day_cells']):
            x = x0 + (idx * cw)
            if cell.get('active'):
                self.set_fill_color(224, 242, 254)
                self.set_text_color(15, 23, 42)
            else:
                self.set_fill_color(241, 245, 249)
                self.set_text_color(203, 213, 225)
            self.set_draw_color(226, 232, 240)
            self.rect(x, y_num, cw, row_num, style='FD')
            self.set_xy(x, y_num + 1.5)
            self.cell(cw, 3, str(cell.get('day') or ''), align='C')

        y_code = y_num + row_num
        for idx, cell in enumerate(box['day_cells']):
            x = x0 + (idx * cw)
            if not cell.get('active'):
                fill = (248, 250, 252)
                fg = (203, 213, 225)
            elif (cell.get('code') or '').lower() == 'off':
                fill = (248, 250, 252)
                fg = (71, 85, 105)
            elif cell.get('code_display') == '✓':
                fill = (236, 253, 245)
                fg = (4, 120, 87)
            else:
                fill = (255, 255, 255)
                fg = (15, 23, 42)
            self.set_fill_color(*fill)
            self.set_text_color(*fg)
            self.set_draw_color(226, 232, 240)
            self.rect(x, y_code, cw, row_code, style='FD')
            self.set_xy(x, y_code + 2)
            display = cell.get('code_display') or '—'
            self.cell(cw, 3, _pdf_text(display), align='C')

        self.set_text_color(0, 0, 0)
        self.set_y(y_code + row_code + 3)

    def _draw_days_summary(self, box: dict[str, Any]) -> None:
        if not box.get('days_str'):
            return
        self.set_font('NotoArabic', '', 9)
        self.set_text_color(71, 85, 105)
        self.cell(0, 5, _shape_ar(f'أيام الدوام: {box["days_str"]}'), ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def _draw_closing(self) -> None:
        self.set_font('NotoArabic', '', 9)
        self.set_text_color(51, 65, 85)
        self.multi_cell(
            0,
            5,
            _shape_ar(
                'هذه وثيقة رسمية صادرة عن نظام الموارد البشرية. '
                'يرجى الالتزام بجدول الدوام المبيّن أعلاه.'
            ),
        )
        self.ln(2)
        self.cell(0, 5, _shape_ar('إدارة الموارد البشرية'), ln=True)
        self.set_text_color(0, 0, 0)


def build_work_schedule_pdf(*, employee, boxes: list[dict[str, Any]]) -> bytes:
    pdf = _WorkSchedulePDF()
    for box in boxes:
        pdf.add_page()
        pdf._draw_doc_header(employee)
        pdf._draw_month_title(box)
        pdf._draw_grid(box)
        pdf._draw_days_summary(box)
        pdf._draw_closing()

    out = pdf.output(dest='S')
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode('latin-1')
