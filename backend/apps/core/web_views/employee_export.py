"""تصدير بيانات الموظف إلى Excel ملوّن (بيانات تبويب الموظف فقط)."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.employees.models import Employee
from apps.core.web_views._helpers import employee_branch_access_required


@login_required
@employee_branch_access_required
def export_employee_salary_excel(request, employee_id):
    """يُنشئ ملف Excel ملوّن يحتوي على بيانات تبويب الموظف فقط."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    employee = get_object_or_404(Employee, id=employee_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "بيانات الموظف"
    ws.sheet_view.rightToLeft = True

    # ──────────── أنماط ────────────
    title_font = Font(name='Arial', size=16, bold=True, color='FFFFFF')
    title_fill = PatternFill('solid', fgColor='1E40AF')

    header_font = Font(name='Arial', size=12, bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='2563EB')

    label_font = Font(name='Arial', size=11, bold=True, color='1E293B')
    label_fill = PatternFill('solid', fgColor='F1F5F9')

    value_font = Font(name='Arial', size=11, color='0F172A')
    value_fill = PatternFill('solid', fgColor='FFFFFF')

    salary_label_fill = PatternFill('solid', fgColor='DBEAFE')
    salary_value_fill = PatternFill('solid', fgColor='EFF6FF')

    allowance_fill = PatternFill('solid', fgColor='ECFDF5')
    allowance_label_fill = PatternFill('solid', fgColor='D1FAE5')

    deduction_fill = PatternFill('solid', fgColor='FEF2F2')
    deduction_label_fill = PatternFill('solid', fgColor='FEE2E2')

    total_font = Font(name='Arial', size=14, bold=True, color='FFFFFF')
    total_fill = PatternFill('solid', fgColor='059669')

    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    right = Alignment(horizontal='right', vertical='center', wrap_text=True)

    thin = Side(border_style='thin', color='CBD5E1')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # ──────────── أعمدة ────────────
    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 32

    # ──────────── العنوان ────────────
    ws.merge_cells('A1:B1')
    c = ws['A1']
    c.value = "بيانات الموظف"
    c.font = title_font
    c.fill = title_fill
    c.alignment = center
    c.border = border
    ws.row_dimensions[1].height = 38

    # تاريخ التصدير
    ws.merge_cells('A2:B2')
    c = ws['A2']
    c.value = f"تاريخ الإصدار: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
    c.font = Font(name='Arial', size=10, italic=True, color='64748B')
    c.alignment = center
    ws.row_dimensions[2].height = 22

    row = 4

    def section_header(text):
        nonlocal row
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        c = ws.cell(row=row, column=1, value=text)
        c.font = header_font
        c.fill = header_fill
        c.alignment = center
        c.border = border
        ws.row_dimensions[row].height = 28
        row += 1

    def kv(label, value, label_fill_=None, value_fill_=None):
        nonlocal row
        c1 = ws.cell(row=row, column=1, value=label)
        c1.font = label_font
        c1.fill = label_fill_ or label_fill
        c1.alignment = right
        c1.border = border

        c2 = ws.cell(row=row, column=2, value=value if value not in (None, '') else '—')
        c2.font = value_font
        c2.fill = value_fill_ or value_fill
        c2.alignment = right
        c2.border = border
        ws.row_dimensions[row].height = 22
        row += 1

    # ──────────── بيانات الموظف (نفس حقول تبويب "بيانات الموظف") ────────────
    section_header("بيانات الموظف")
    kv("الاسم", employee.name)
    kv("رقم الموظف", employee.employee_number)
    kv("رقم الهوية", employee.id_number)
    kv("الجوال", employee.phone)
    kv("البريد الإلكتروني", employee.email)
    kv("الجنسية", getattr(employee.nationality, 'name', None))
    kv("المهنة", getattr(employee.profession, 'name', None))
    kv("الكفالة", getattr(employee.sponsorship, 'name', None))
    kv("الفرع", getattr(employee.branch, 'name', None))
    kv("القسم", getattr(employee.department, 'name', None))
    kv("مركز التكلفة", getattr(employee.cost_center, 'name', None))
    kv("تاريخ المباشرة", employee.hire_date)
    kv("تاريخ الانتهاء", employee.end_date)
    kv("تاريخ انتهاء الجواز", employee.passport_expiry_date)
    kv("التأمين", getattr(employee.insurance, 'name', None))
    kv("فئة التأمين", getattr(employee.insurance_class, 'name', None))
    kv("الحالة", employee.get_status_display())
    kv("سبب الانتهاء", employee.end_reason)

    # ──────────── إخراج الملف ────────────
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    safe_name = (employee.name or 'employee').replace(' ', '_')
    filename = f"employee_{safe_name}_{timezone.now().strftime('%Y%m%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
