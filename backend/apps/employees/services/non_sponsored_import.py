"""استيراد موظفين بدون كفالة من Excel بنفس أعمدة التصدير."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.models import Branch
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department
from apps.employees.models import Employee
from apps.setup.models import Administration, Nationality, Profession

# يطابق `_NO_SPONSORSHIP_COLUMNS` في employee_export.py
HEADER_TO_FIELD = {
    'الاسم': 'name',
    'رقم الهوية': 'id_number',
    'رقم الجوال': 'phone',
    'الجوال': 'phone',
    'الرقم الوظيفي': 'employee_number',
    'رقم الموظف': 'employee_number',
    'تاريخ المباشرة': 'hire_date',
    'الجنسية': 'nationality',
    'المهنة': 'profession',
    'الراتب الأساسي': 'basic_salary',
    'الفرع': 'branch',
    'القسم': 'department',
    'الإدارة': 'administration',
    'مركز التكلفة': 'cost_center',
}


@dataclass
class ImportRowResult:
    row_number: int
    action: str  # created | updated | skipped | error
    message: str
    employee_number: str = ''


@dataclass
class ImportSummary:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    results: list[ImportRowResult] = field(default_factory=list)


def _norm_header(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip().replace('\n', ' ')


def _cell_str(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text in {'—', '-', '–', 'N/A', 'n/a'}:
        return ''
    return text


def _cell_date(value: Any) -> date | None:
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _cell_str(value)
    if not text:
        return None
    text = text[:10]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'تاريخ غير صالح: {value!r}')


def _cell_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    text = _cell_str(value).replace(',', '')
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'رقم غير صالح: {value!r}') from exc


def _lookup_by_name_or_code(qs, raw: str):
    text = (raw or '').strip()
    if not text:
        return None
    obj = qs.filter(name__iexact=text).first()
    if obj:
        return obj
    if hasattr(qs.model, 'code'):
        obj = qs.filter(code__iexact=text).first()
        if obj:
            return obj
    return None


def _resolve_administration(raw: str) -> Administration | None:
    text = (raw or '').strip()
    if not text:
        return None
    qs = Administration.objects.filter(is_deleted=False, is_active=True)
    if '—' in text or '-' in text:
        parts = [p.strip() for p in text.replace('—', '-').split('-', 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            obj = qs.filter(code__iexact=parts[0], name__iexact=parts[1]).first()
            if obj:
                return obj
            obj = qs.filter(code__iexact=parts[0]).first()
            if obj:
                return obj
    return _lookup_by_name_or_code(qs, text)


def _resolve_branch(raw: str, *, allowed_ids: set[int] | None) -> Branch | None:
    qs = Branch.objects.filter(is_deleted=False, is_active=True)
    if allowed_ids is not None:
        qs = qs.filter(pk__in=allowed_ids)
    return _lookup_by_name_or_code(qs, raw)


def _parse_header_map(header_row) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        label = _norm_header(cell)
        field = HEADER_TO_FIELD.get(label)
        if field and field not in mapping:
            mapping[field] = idx
    return mapping


def _row_dict(row, header_map: dict[str, int]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field, idx in header_map.items():
        data[field] = row[idx] if idx < len(row) else None
    return data


def _find_existing(
    employee_number: str,
    id_number: str,
    *,
    allowed_branch_ids: set[int] | None,
) -> Employee | None:
    def _lookup(**kwargs) -> Employee | None:
        qs = Employee.objects.filter(is_deleted=False, **kwargs)
        emp = qs.first()
        if emp is None:
            return None
        if allowed_branch_ids is not None and emp.branch_id not in allowed_branch_ids:
            raise ValueError(
                f'الموظف موجود في فرع خارج صلاحيتك ({emp.employee_number or emp.id_number})',
            )
        return emp

    if employee_number:
        emp = _lookup(employee_number=employee_number)
        if emp:
            return emp
    if id_number:
        return _lookup(id_number=id_number)
    return None


def import_non_sponsored_employees_from_workbook(
    workbook,
    *,
    user,
    allowed_branch_ids: set[int] | None,
    apply_salary: bool = True,
) -> ImportSummary:
    """
    يستورد صفوف الشيت الأول بنفس أعمدة التصدير.
    - ينشئ موظفاً جديداً أو يحدّث موجوداً (بدون كفالة فقط).
    - يتخطى موظفاً مسجّلاً على كفالة.
    """
    summary = ImportSummary()
    ws = workbook.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        summary.errors += 1
        summary.results.append(ImportRowResult(1, 'error', 'الملف فارغ'))
        return summary

    header_map = _parse_header_map(rows[0])
    if 'name' not in header_map:
        summary.errors += 1
        summary.results.append(
            ImportRowResult(1, 'error', 'عمود «الاسم» مطلوب في الصف الأول'),
        )
        return summary

    nat_qs = Nationality.objects.filter(is_deleted=False, is_active=True)
    prof_qs = Profession.objects.filter(is_deleted=False, is_active=True)
    dept_qs = Department.objects.filter(is_deleted=False, is_active=True)
    cc_qs = CostCenter.objects.filter(is_deleted=False, is_active=True)

    for excel_row_num, row in enumerate(rows[1:], start=2):
        if row is None or all(c is None or str(c).strip() == '' for c in row):
            continue
        raw = _row_dict(row, header_map)
        name = _cell_str(raw.get('name'))
        if not name:
            summary.skipped += 1
            summary.results.append(
                ImportRowResult(excel_row_num, 'skipped', 'اسم فارغ — تم التخطي'),
            )
            continue

        try:
            employee_number = _cell_str(raw.get('employee_number'))
            id_number = _cell_str(raw.get('id_number'))
            phone = _cell_str(raw.get('phone'))
            hire_date = _cell_date(raw.get('hire_date')) if 'hire_date' in header_map else None
            basic_salary = (
                _cell_decimal(raw.get('basic_salary'))
                if apply_salary and 'basic_salary' in header_map
                else None
            )

            branch = None
            if 'branch' in header_map:
                branch_raw = _cell_str(raw.get('branch'))
                if branch_raw:
                    branch = _resolve_branch(branch_raw, allowed_ids=allowed_branch_ids)
                    if branch is None:
                        raise ValueError(f'الفرع غير موجود أو خارج صلاحيتك: {branch_raw}')

            if allowed_branch_ids is not None and branch is not None:
                if branch.pk not in allowed_branch_ids:
                    raise ValueError(f'لا صلاحية على الفرع: {branch.name}')

            nationality = (
                _lookup_by_name_or_code(nat_qs, _cell_str(raw.get('nationality')))
                if 'nationality' in header_map else None
            )
            profession = (
                _lookup_by_name_or_code(prof_qs, _cell_str(raw.get('profession')))
                if 'profession' in header_map else None
            )
            department = (
                _lookup_by_name_or_code(dept_qs, _cell_str(raw.get('department')))
                if 'department' in header_map else None
            )
            cost_center = (
                _lookup_by_name_or_code(cc_qs, _cell_str(raw.get('cost_center')))
                if 'cost_center' in header_map else None
            )
            administration = (
                _resolve_administration(_cell_str(raw.get('administration')))
                if 'administration' in header_map else None
            )
            if 'nationality' in header_map and _cell_str(raw.get('nationality')) and not nationality:
                raise ValueError(f'الجنسية غير موجودة: {_cell_str(raw.get("nationality"))}')
            if 'profession' in header_map and _cell_str(raw.get('profession')) and not profession:
                raise ValueError(f'المهنة غير موجودة: {_cell_str(raw.get("profession"))}')
            if 'department' in header_map and _cell_str(raw.get('department')) and not department:
                raise ValueError(f'القسم غير موجود: {_cell_str(raw.get("department"))}')
            if 'cost_center' in header_map and _cell_str(raw.get('cost_center')) and not cost_center:
                raise ValueError(f'مركز التكلفة غير موجود: {_cell_str(raw.get("cost_center"))}')
            if 'administration' in header_map and _cell_str(raw.get('administration')) and not administration:
                raise ValueError(f'الإدارة غير موجودة: {_cell_str(raw.get("administration"))}')

            existing = _find_existing(
                employee_number,
                id_number,
                allowed_branch_ids=allowed_branch_ids,
            )
            if existing and existing.sponsorship_id:
                summary.skipped += 1
                summary.results.append(
                    ImportRowResult(
                        excel_row_num,
                        'skipped',
                        f'الموظف «{existing.name}» على كفالة — لم يُعدَّل',
                        employee_number=existing.employee_number or '',
                    ),
                )
                continue

            with transaction.atomic():
                if existing:
                    emp = existing
                    action = 'updated'
                else:
                    emp = Employee(
                        status=Employee.Status.ACTIVE,
                    )
                    action = 'created'

                emp.name = name
                emp.sponsorship = None
                if employee_number:
                    emp.employee_number = employee_number
                if id_number:
                    emp.id_number = id_number
                if phone:
                    emp.phone = phone
                if hire_date is not None:
                    emp.hire_date = hire_date
                if branch is not None:
                    emp.branch = branch
                elif action == 'created' and allowed_branch_ids is not None and len(allowed_branch_ids) == 1:
                    emp.branch_id = next(iter(allowed_branch_ids))
                if nationality is not None:
                    emp.nationality = nationality
                if profession is not None:
                    emp.profession = profession
                if department is not None:
                    emp.department = department
                if administration is not None:
                    emp.administration = administration
                if cost_center is not None:
                    emp.cost_center = cost_center
                if basic_salary is not None:
                    emp.basic_salary = basic_salary

                if action == 'created' and emp.branch_id is None and allowed_branch_ids is not None:
                    raise ValueError('الفرع مطلوب عند إنشاء موظف جديد')

                emp.updated_at = timezone.now()
                emp.save()

            if action == 'created':
                summary.created += 1
            else:
                summary.updated += 1
            summary.results.append(
                ImportRowResult(
                    excel_row_num,
                    action,
                    f'تم {"الإنشاء" if action == "created" else "التحديث"}: {emp.name}',
                    employee_number=emp.employee_number or '',
                ),
            )
        except Exception as exc:
            summary.errors += 1
            summary.results.append(
                ImportRowResult(
                    excel_row_num,
                    'error',
                    str(exc),
                    employee_number=_cell_str(raw.get('employee_number')),
                ),
            )

    return summary


def import_non_sponsored_employees_from_upload(uploaded_file, *, user, allowed_branch_ids, apply_salary=True) -> ImportSummary:
    from openpyxl import load_workbook

    wb = load_workbook(uploaded_file, data_only=True)
    try:
        return import_non_sponsored_employees_from_workbook(
            wb,
            user=user,
            allowed_branch_ids=allowed_branch_ids,
            apply_salary=apply_salary,
        )
    finally:
        wb.close()
