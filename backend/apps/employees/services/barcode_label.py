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
    def padding_mm(self) -> float:
        return max(1.5, min(4.0, self.height_mm * 0.06))

    @property
    def name_font_pt(self) -> float:
        return round(max(6.0, min(18.0, self.height_mm * 0.28)), 1)

    @property
    def number_font_pt(self) -> float:
        return round(max(5.0, min(14.0, self.height_mm * 0.22)), 1)

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
    """أوامر ZPL بمقاس ديناميكي (203 DPI)."""
    copies = max(1, min(int(copies or 1), MAX_COPIES))
    bc = _zpl_safe_text(label.barcode_value, max_len=MAX_BARCODE_LEN)
    num_line = _zpl_safe_text(label.number_display, max_len=40)
    name_line = _zpl_safe_text(label.name, max_len=40)

    scale = dims.height_mm / DEFAULT_LABEL_HEIGHT_MM
    margin_x = max(10, int(30 * (dims.width_mm / DEFAULT_LABEL_WIDTH_MM)))
    name_y = max(8, int(18 * scale))
    name_h = max(14, int(22 * scale))
    num_y = name_y + name_h + max(4, int(6 * scale))
    num_h = max(12, int(20 * scale))
    bc_y = num_y + num_h + max(4, int(8 * scale))
    bc_height = max(24, mm_to_dots(dims.barcode_height_mm) - 8)
    bar_w = max(1, min(4, int(round(dims.width_mm / 40))))

    lines = [
        '^XA',
        f'^PW{dims.width_dots}',
        f'^LL{dims.height_dots}',
        '^LH0,0',
        '^CI28',
    ]
    if name_line:
        lines.append(f'^FO{margin_x},{name_y}^A0N,{name_h},{name_h}^FD{name_line}^FS')
    if num_line:
        lines.append(f'^FO{margin_x},{num_y}^A0N,{num_h},{num_h}^FD{num_line}^FS')
    lines.extend([
        f'^FO{margin_x},{bc_y}^BY{bar_w},2,{bc_height}^BCN,{bc_height},Y,N,N^FD{bc}^FS',
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
