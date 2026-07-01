"""ملصق باركود الموظف — Zebra مع مقاسات قابلة للتعديل (Code128)."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from apps.employees.models import Employee

ZEBRA_DPI = 203
DEFAULT_LABEL_WIDTH_MM = 100.0
DEFAULT_LABEL_HEIGHT_MM = 40.0
MIN_LABEL_WIDTH_MM = 30.0
MAX_LABEL_WIDTH_MM = 150.0
MIN_LABEL_HEIGHT_MM = 15.0
MAX_LABEL_HEIGHT_MM = 100.0
MAX_COPIES = 50
MAX_BARCODE_LEN = 48


@dataclass(frozen=True)
class LabelDimensions:
    width_mm: float
    height_mm: float

    @property
    def name_font_pt(self) -> float:
        """حجم خط اسم الشركة (السطر الأول)."""
        by_h = self.height_mm * 0.20
        by_w = self.width_mm * 0.10
        return round(max(6.5, min(14.0, min(by_h, by_w))), 1)

    @property
    def company_font_pt(self) -> float:
        """حجم خط اسم الموظف (السطر الثاني)."""
        by_h = self.height_mm * 0.17
        by_w = self.width_mm * 0.085
        return round(max(6.0, min(11.0, min(by_h, by_w))), 1)

    @property
    def number_font_pt(self) -> float:
        """حجم خط الرقم الوظيفي."""
        return round(max(7.0, min(14.0, self.height_mm * 0.22)), 1)

    @property
    def padding_mm(self) -> float:
        return max(1.2, min(3.0, self.height_mm * 0.05))

    @property
    def barcode_height_mm(self) -> float:
        """ارتفاع منطقة الباركود — يتمدد مع ارتفاع الملصق."""
        reserved = self.padding_mm * 2 + self.name_font_pt * 0.38 + self.number_font_pt * 0.38
        return max(6.0, self.height_mm - reserved)

    @property
    def barcode_width_mm(self) -> float:
        return max(20.0, self.width_mm - self.padding_mm * 2)

    @property
    def width_dots(self) -> int:
        return mm_to_dots(self.width_mm)

    @property
    def height_dots(self) -> int:
        return mm_to_dots(self.height_mm)

    def query_params(self, *, copies: int | None = None) -> dict[str, str]:
        params = {
            'w': self._fmt(self.width_mm),
            'h': self._fmt(self.height_mm),
        }
        if copies is not None:
            params['copies'] = str(copies)
        return params

    @staticmethod
    def _fmt(value: float) -> str:
        text = f'{value:.1f}'.rstrip('0').rstrip('.')
        return text or '0'


@dataclass(frozen=True)
class EmployeeBarcodeLabel:
    employee_id: int
    name: str
    company_name: str
    employee_number: str
    barcode_value: str
    number_display: str
    barcode_svg: str


def mm_to_dots(mm: float, *, dpi: int = ZEBRA_DPI) -> int:
    return max(1, int(round(float(mm) * dpi / 25.4)))


def _clamp_mm(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def parse_label_dimensions(
    width_raw: str | float | None = None,
    height_raw: str | float | None = None,
) -> LabelDimensions:
    try:
        w = float((width_raw if width_raw not in (None, '') else DEFAULT_LABEL_WIDTH_MM))
    except (TypeError, ValueError):
        w = DEFAULT_LABEL_WIDTH_MM
    try:
        h = float((height_raw if height_raw not in (None, '') else DEFAULT_LABEL_HEIGHT_MM))
    except (TypeError, ValueError):
        h = DEFAULT_LABEL_HEIGHT_MM
    return LabelDimensions(
        width_mm=round(_clamp_mm(w, MIN_LABEL_WIDTH_MM, MAX_LABEL_WIDTH_MM), 1),
        height_mm=round(_clamp_mm(h, MIN_LABEL_HEIGHT_MM, MAX_LABEL_HEIGHT_MM), 1),
    )


def barcode_value_for_employee(employee: Employee) -> str:
    """قيمة الباركود: الرقم الوظيفي ثم الهوية ثم معرف السجل."""
    num = (employee.employee_number or '').strip()
    if num:
        return num[:MAX_BARCODE_LEN]
    idn = (employee.id_number or '').strip()
    if idn:
        return idn[:MAX_BARCODE_LEN]
    return str(employee.pk)


def build_barcode_svg(value: str, *, dims: LabelDimensions) -> str:
    """SVG لباركود Code128 — يتكيّف مع مقاس الملصق."""
    from barcode import Code128
    from barcode.writer import SVGWriter
    from io import BytesIO

    safe = (value or '').strip()
    if not safe:
        return ''
    module_width = max(0.12, min(0.55, dims.barcode_width_mm / max(len(safe) * 12, 80)))
    module_height = max(4.0, dims.barcode_height_mm * 0.88)
    writer = SVGWriter()
    writer.set_options({
        'module_width': module_width,
        'module_height': module_height,
        'quiet_zone': max(1.0, dims.width_mm * 0.015),
        'write_text': False,
        'dpi': ZEBRA_DPI,
    })
    buffer = BytesIO()
    Code128(safe, writer=writer).write(buffer)
    svg = buffer.getvalue().decode('utf-8')
    # تمديد الباركود ليملأ عرض الحاوية في المتصفح
    if '<svg' in svg and 'preserveAspectRatio' not in svg:
        svg = svg.replace('<svg ', '<svg preserveAspectRatio="none" ', 1)
    return svg


def sponsorship_company_for_employee(employee: Employee) -> str:
    """اسم شركة الكفالة المرتبطة بالموظف."""
    sponsorship = getattr(employee, 'sponsorship', None)
    if sponsorship and (sponsorship.company_name or '').strip():
        return sponsorship.company_name.strip()
    branch = getattr(employee, 'branch', None)
    company = getattr(branch, 'company', None) if branch else None
    if company and (company.name or '').strip():
        return company.name.strip()
    return '—'


def build_employee_barcode_label(
    employee: Employee,
    *,
    dims: LabelDimensions | None = None,
) -> EmployeeBarcodeLabel:
    size = dims or parse_label_dimensions(None, None)
    num = (employee.employee_number or '').strip()
    bc = barcode_value_for_employee(employee)
    display = num if num else bc
    return EmployeeBarcodeLabel(
        employee_id=employee.pk,
        name=(employee.name or '—').strip(),
        company_name=sponsorship_company_for_employee(employee),
        employee_number=num or '—',
        barcode_value=bc,
        number_display=display,
        barcode_svg=build_barcode_svg(bc, dims=size),
    )


def _zpl_safe_text(value: str, *, max_len: int = 80) -> str:
    cleaned = (value or '').replace('^', ' ').replace('~', ' ').replace('\\', ' ')
    return cleaned.strip()[:max_len]


def build_zpl_label(
    label: EmployeeBarcodeLabel,
    *,
    dims: LabelDimensions,
    copies: int = 1,
) -> str:
    """أوامر ZPL — شركة الكفالة + اسم الموظف + الرقم الوظيفي."""
    copies = max(1, min(int(copies or 1), MAX_COPIES))
    name_line = _zpl_safe_text(label.name, max_len=60)
    company_line = _zpl_safe_text(label.company_name, max_len=80)
    num_line = _zpl_safe_text(label.number_display, max_len=40)

    margin_x = max(8, int(16 * (dims.width_mm / DEFAULT_LABEL_WIDTH_MM)))
    text_w = max(20, dims.width_dots - margin_x * 2)
    company_h = max(14, int(dims.height_dots * 0.20))
    name_h = max(12, int(dims.height_dots * 0.14))
    num_h = max(14, int(dims.height_dots * 0.18))
    gap = max(3, int(dims.height_dots * 0.03))
    company_lines = max(1, min(2, int(len(company_line) / 22) + 1))
    name_lines = 1 if len(name_line) <= 24 else 2
    block_h = (
        company_h * company_lines
        + gap
        + name_h * name_lines
        + gap
        + num_h
    )
    company_y = max(4, (dims.height_dots - block_h) // 2)
    name_y = company_y + company_h * company_lines + gap
    num_y = name_y + name_h * name_lines + gap

    lines = [
        '^XA',
        f'^PW{dims.width_dots}',
        f'^LL{dims.height_dots}',
        '^LH0,0',
        '^CI28',
    ]
    if company_line:
        lines.append(
            f'^FO{margin_x},{company_y}^A0N,{company_h},{company_h}'
            f'^FB{text_w},{company_lines},0,C,0^FD{company_line}^FS'
        )
    if name_line:
        lines.append(
            f'^FO{margin_x},{name_y}^A0N,{name_h},{name_h}'
            f'^FB{text_w},{name_lines},0,C,0^FD{name_line}^FS'
        )
    if num_line:
        lines.append(
            f'^FO{margin_x},{num_y}^A0N,{num_h},{num_h}'
            f'^FB{text_w},1,0,C,0^FD{num_line}^FS'
        )
    lines.extend([
        f'^PQ{copies}',
        '^XZ',
    ])
    return '\n'.join(lines) + '\n'


def parse_copies(raw: str | None, *, default: int = 1) -> int:
    try:
        n = int((raw or '').strip() or default)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_COPIES))


def label_size_querystring(
    dims: LabelDimensions,
    *,
    copies: int | None = None,
    extra: dict | None = None,
) -> str:
    params = dict(dims.query_params(copies=copies))
    if extra:
        params.update({k: v for k, v in extra.items() if v is not None and v != ''})
    return urlencode(params)
