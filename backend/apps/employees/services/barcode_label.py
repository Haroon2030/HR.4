"""ملصق باركود الموظف — Zebra 10×4 سم (Code128)."""
from __future__ import annotations

from dataclasses import dataclass

from apps.employees.models import Employee

# 10 سم × 4 سم عند 203 DPI (طابعة Zebra شائعة)
ZEBRA_LABEL_WIDTH_DOTS = 799
ZEBRA_LABEL_HEIGHT_DOTS = 320
MAX_COPIES = 50
MAX_BARCODE_LEN = 48


@dataclass(frozen=True)
class EmployeeBarcodeLabel:
    employee_id: int
    name: str
    employee_number: str
    barcode_value: str
    number_display: str
    barcode_svg: str


def barcode_value_for_employee(employee: Employee) -> str:
    """قيمة الباركود: الرقم الوظيفي ثم الهوية ثم معرف السجل."""
    num = (employee.employee_number or '').strip()
    if num:
        return num[:MAX_BARCODE_LEN]
    idn = (employee.id_number or '').strip()
    if idn:
        return idn[:MAX_BARCODE_LEN]
    return str(employee.pk)


def build_barcode_svg(value: str) -> str:
    """SVG لباركود Code128 — مناسب للطباعة 203 DPI."""
    from barcode import Code128
    from barcode.writer import SVGWriter
    from io import BytesIO

    safe = (value or '').strip()
    if not safe:
        return ''
    writer = SVGWriter()
    writer.set_options({
        'module_width': 0.28,
        'module_height': 10.0,
        'quiet_zone': 2.0,
        'write_text': False,
        'dpi': 203,
    })
    buffer = BytesIO()
    Code128(safe, writer=writer).write(buffer)
    return buffer.getvalue().decode('utf-8')


def build_employee_barcode_label(employee: Employee) -> EmployeeBarcodeLabel:
    num = (employee.employee_number or '').strip()
    bc = barcode_value_for_employee(employee)
    display = num if num else bc
    return EmployeeBarcodeLabel(
        employee_id=employee.pk,
        name=(employee.name or '—').strip(),
        employee_number=num or '—',
        barcode_value=bc,
        number_display=display,
        barcode_svg=build_barcode_svg(bc),
    )


def _zpl_safe_text(value: str, *, max_len: int = 80) -> str:
    """إزالة أحرف ZPL الخاصة — للنصوص اللاتينية/الأرقام في ZPL."""
    cleaned = (value or '').replace('^', ' ').replace('~', ' ').replace('\\', ' ')
    return cleaned.strip()[:max_len]


def build_zpl_label(label: EmployeeBarcodeLabel, *, copies: int = 1) -> str:
    """
    أوامر ZPL لملصق 100×40 مم.
    ملاحظة: الاسم العربي يُطبَع بدقة أعلى عبر طباعة المتصفح؛ ZPL يتضمن الرقم والباركود.
    """
    copies = max(1, min(int(copies or 1), MAX_COPIES))
    bc = _zpl_safe_text(label.barcode_value, max_len=MAX_BARCODE_LEN)
    num_line = _zpl_safe_text(label.number_display, max_len=40)
    name_line = _zpl_safe_text(label.name, max_len=40)

    lines = [
        '^XA',
        f'^PW{ZEBRA_LABEL_WIDTH_DOTS}',
        f'^LL{ZEBRA_LABEL_HEIGHT_DOTS}',
        '^LH0,0',
        '^CI28',
    ]
    if name_line:
        lines.append(f'^FO30,18^A0N,22,22^FD{name_line}^FS')
    if num_line:
        lines.append(f'^FO30,48^A0N,20,20^FD{num_line}^FS')
    lines.extend([
        f'^FO30,78^BY2,2,72^BCN,72,Y,N,N^FD{bc}^FS',
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
