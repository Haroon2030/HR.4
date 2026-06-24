"""استخراج تفاصيل الحقول المتغيرة من سجلات simple_history."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# حقول لا تُعرض قيمها (أمان / حجم)
SENSITIVE_FIELDS = frozenset({
    'password',
    'last_login',
    'secret',
    'token',
    'key',
})

HISTORY_META_FIELDS = frozenset({
    'history_date',
    'history_user',
    'history_change_reason',
    'history_type',
    'history_id',
    'history_relation',
})

# تسمية النموذج من اسم كلاس Historical*
MODEL_LABELS: dict[str, str] = {
    'Employee': 'موظف',
    'PendingAction': 'طلب عملية',
    'PayrollRun': 'مسير رواتب',
    'UserProfile': 'ملف مستخدم',
    'EmployeeLedger': 'سجل مخصصات',
    'Role': 'دور',
    'Branch': 'فرع',
}

# تسميات عربية للحقول
FIELD_LABELS: dict[str, str] = {
    'username': 'اسم المستخدم',
    'first_name': 'الاسم الأول',
    'last_name': 'اسم العائلة',
    'email': 'البريد',
    'is_active': 'نشط',
    'is_staff': 'موظف إدارة',
    'is_superuser': 'مدير نظام',
    'role_id': 'الدور',
    'role': 'الدور',
    'branch_id': 'الفرع',
    'branch': 'الفرع',
    'user_number': 'رقم المستخدم',
    'phone': 'الهاتف',
    'position': 'المنصب',
    'department_id': 'القسم',
    'department': 'القسم',
    'name': 'الاسم',
    'status': 'الحالة',
    'action_type': 'نوع العملية',
    'period_year': 'سنة المسير',
    'period_month': 'شهر المسير',
    'is_protected': 'محمي',
    'is_deleted': 'محذوف',
    'deleted_at': 'تاريخ الحذف',
    'notes': 'ملاحظات',
    'description': 'الوصف',
    'work_schedule': 'جدول الدوام',
    'id_document': 'مستند الهوية',
    'passport_document': 'جواز السفر',
    'commencement_document': 'مستند المباشرة',
    'health_card_document': 'البطاقة الصحية',
    'basic_salary': 'الراتب الأساسي',
    'housing_allowance': 'بدل السكن',
    'transport_allowance': 'بدل النقل',
    'other_allowance': 'بدلات أخرى',
    'cash_amount': 'كاش',
    'meal_allowance': 'بدل التغذية',
    'hire_date': 'تاريخ المباشرة',
    'end_date': 'تاريخ الانتهاء',
    'iban': 'الآيبان',
    'user_id': 'المستخدم',
    'employee_id': 'الموظف',
    'nationality_id': 'الجنسية',
    'sponsorship_id': 'الكفالة',
    'available_leave_balance': 'رصيد الإجازة المستخدم',
    'leave_accrual_start_date': 'تاريخ بدء احتساب الإجازة',
    'opening_leave_days': 'رصيد إجازة افتتاحي',
    'opening_eosb_amount': 'مخصص نهاية خدمة افتتاحي',
    'migration_locked': 'اعتماد أرصدة الترحيل',
}


@dataclass(frozen=True)
class AuditChangeLine:
    label: str
    old: str
    new: str

    @property
    def inline(self) -> str:
        """سطر واحد مضغوط للعرض في الجدول."""
        if self.old in ('—', '') and self.new not in ('—', ''):
            return f'{self.label}: +{self.new}'
        if self.new in ('—', '') and self.old not in ('—', ''):
            return f'{self.label}: −{self.old}'
        return f'{self.label}: {self.old}→{self.new}'


def _is_meaningless_change(old_v: str, new_v: str, raw_old: Any = None, raw_new: Any = None) -> bool:
    if raw_old is not None and raw_new is not None and raw_old == raw_new:
        return True
    if old_v == new_v:
        return True
    empty = frozenset({'—', '', '[مخفي]'})
    return old_v in empty and new_v in empty


def _model_label_ar(history_row, entity_label: str | None = None) -> str:
    if entity_label:
        return entity_label
    cls_name = history_row.__class__.__name__
    if cls_name.startswith('Historical'):
        base = cls_name[len('Historical'):]
        if base in MODEL_LABELS:
            return MODEL_LABELS[base]
    vn = str(getattr(history_row._meta, 'verbose_name', '') or '')
    low = vn.lower()
    if low.startswith('historical '):
        rest = vn.split(' ', 1)[-1].strip()
        return MODEL_LABELS.get(rest, rest)
    return vn or 'سجل'


def _label(field: str) -> str:
    if field.endswith('_id') and field[:-3] in FIELD_LABELS:
        return FIELD_LABELS[field[:-3]]
    return FIELD_LABELS.get(field, field.replace('_', ' '))


def _basename(value: Any) -> str:
    if value is None or value == '':
        return '—'
    text = str(value).replace('\\', '/').strip()
    return os.path.basename(text) or text


def _summarize_work_schedule(value: Any) -> str:
    if value is None or value == '':
        return '—'
    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        raw = str(value)
        return raw[:100] + '…' if len(raw) > 100 else raw

    if not isinstance(data, dict):
        return '—'

    boxes = data.get('boxes') or []
    if not isinstance(boxes, list) or not boxes:
        ver = data.get('version', '')
        return f'جدول دوام فارغ (إصدار {ver})' if ver else 'جدول دوام فارغ'

    months: list[str] = []
    for box in boxes[:6]:
        if not isinstance(box, dict):
            continue
        y = box.get('year', '?')
        m = box.get('month', '?')
        months.append(f'{m}/{y}')
    extra = len(boxes) - len(months)
    tail = f' (+{extra} شهر)' if extra > 0 else ''
    return f'{len(boxes)} شهر: {", ".join(months)}{tail}'


def _work_schedule_diff(old_raw: Any, new_raw: Any) -> tuple[str, str]:
    old_s = _summarize_work_schedule(old_raw)
    new_s = _summarize_work_schedule(new_raw)
    if old_s == new_s and old_raw != new_raw:
        return 'جدول سابق', 'جدول مُحدَّث'
    return old_s, new_s


def _format_value(field: str, value: Any) -> str:
    if field in SENSITIVE_FIELDS:
        return '[مخفي]'

    if field == 'work_schedule':
        return _summarize_work_schedule(value)

    if field.endswith('_document') or field.endswith('_file') or field == 'logo':
        return _basename(value)

    if value is None or value == '':
        return '—'

    if isinstance(value, bool):
        return 'نعم' if value else 'لا'

    if field.endswith('_salary') or field.endswith('_allowance') or field in (
        'cash_amount', 'deduction_amount', 'total_salary', 'gross_salary', 'net_salary',
    ):
        try:
            return f'{Decimal(str(value)):.2f} ر.س'
        except Exception:
            pass

    text = str(value).strip()
    if len(text) > 120:
        return text[:117] + '…'
    return text


def summarize_history_changes(
    history_row,
    *,
    entity_label: str | None = None,
    lightweight: bool = False,
) -> tuple[str, str, list[AuditChangeLine]]:
    """
    يُرجع (operation_ar, details نص مختصر, detail_lines للعرض المنظم).
    lightweight=True يتخطى prev_record لتفادي N+1 في لوحات القائمة.
    """
    model_label = _model_label_ar(history_row, entity_label)
    hist_type = getattr(history_row, 'history_type', '') or ''

    if hist_type == '+':
        return f'إنشاء {model_label}', 'إنشاء سجل جديد في النظام', []

    if hist_type == '-':
        return f'حذف {model_label}', 'حذف السجل من النظام', []

    if lightweight:
        return f'تعديل {model_label}', 'تعديل حقول السجل', []

    prev = getattr(history_row, 'prev_record', None)
    if prev is None:
        return f'تعديل {model_label}', 'تعديل — لا يتوفر سجل سابق للمقارنة', []

    try:
        delta = history_row.diff_against(prev)
    except Exception:
        return f'تعديل {model_label}', 'تعديل — تعذر حساب الفروقات', []

    lines: list[AuditChangeLine] = []
    for change in delta.changes:
        field = change.field
        if field in HISTORY_META_FIELDS:
            continue

        label = _label(field)

        if field == 'work_schedule':
            old_v, new_v = _work_schedule_diff(change.old, change.new)
        else:
            old_v = _format_value(field, change.old)
            new_v = _format_value(field, change.new)

        if _is_meaningless_change(old_v, new_v, change.old, change.new):
            continue

        lines.append(AuditChangeLine(label=label, old=old_v, new=new_v))

    if not lines:
        return (
            f'تعديل {model_label}',
            'تعديل — لم تُكتشف حقول متغيرة (قد يكون ربط M2M أو حفظ بدون تغيير)',
            [],
        )

    short_parts = [f'{ln.label}: {ln.old} → {ln.new}' for ln in lines[:4]]
    if len(lines) > 4:
        short_parts.append(f'… +{len(lines) - 4} حقول أخرى')
    details_short = ' | '.join(short_parts)

    return f'تعديل {model_label}', details_short, lines
