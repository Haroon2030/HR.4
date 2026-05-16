"""استخراج تفاصيل الحقول المتغيرة من سجلات simple_history."""
from __future__ import annotations

from typing import Any

# حقول لا تُعرض قيمها (أمان / حجم)
SENSITIVE_FIELDS = frozenset({
    'password',
    'last_login',
    'secret',
    'token',
    'key',
})

# تسميات عربية لحقول شائعة
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
}


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace('_', ' '))


def _format_value(field: str, value: Any) -> str:
    if field in SENSITIVE_FIELDS:
        return '[مخفي]'
    if value is None or value == '':
        return '—'
    if isinstance(value, bool):
        return 'نعم' if value else 'لا'
    text = str(value)
    if len(text) > 80:
        return text[:77] + '…'
    return text


def summarize_history_changes(history_row) -> tuple[str, str]:
    """
    يُرجع (operation_ar, details) لصف تاريخي واحد.
    """
    hist_type = getattr(history_row, 'history_type', '') or ''
    model_label = getattr(history_row, '_meta', None)
    model_label = getattr(model_label, 'verbose_name', 'سجل') if model_label else 'سجل'

    if hist_type == '+':
        return f'إنشاء {model_label}', 'إنشاء سجل جديد في النظام'

    if hist_type == '-':
        return f'حذف {model_label}', 'حذف السجل من النظام'

    prev = getattr(history_row, 'prev_record', None)
    if prev is None:
        return f'تعديل {model_label}', 'تعديل — لا يتوفر سجل سابق للمقارنة'

    try:
        delta = history_row.diff_against(prev)
    except Exception:
        return f'تعديل {model_label}', 'تعديل — تعذر حساب الفروقات'

    parts: list[str] = []
    for change in delta.changes:
        field = change.field
        if field in ('history_date', 'history_user', 'history_change_reason', 'history_type', 'history_id'):
            continue
        if field.endswith('_id') and field[:-3] in FIELD_LABELS:
            label = FIELD_LABELS[field[:-3]]
        else:
            label = _label(field)
        old_v = _format_value(field, change.old)
        new_v = _format_value(field, change.new)
        parts.append(f'{label}: {old_v} → {new_v}')

    if not parts:
        return f'تعديل {model_label}', 'تعديل — لم تُكتشف حقول متغيرة (قد يكون ربط M2M أو حفظ بدون تغيير)'

    return f'تعديل {model_label}', ' | '.join(parts)
