"""
صلاحيات أنواع النماذج الرسمية — وحدة مستقلة لكل نموذج (hr_form_<key>.view)، بنفس فكرة تبويبات الموظف.

إن لم يُمنح المستخدم أي صلاحية نموذج، يُعتمد على السلوك القديم (كل النماذج،
وتُخفى نماذج الرواتب عمّن لا يملك صلاحية الرواتب) — توافق مع التثبيتات القديمة.
"""
from __future__ import annotations

from apps.core.permissions_registry import register_module, register_permission

# (key, الاسم الظاهر في مصفوفة الصلاحيات) — يجب أن يطابق مفاتيح HR_FORMS
# (يتحقق من ذلك اختبار في tests_hr_form_permissions.py)
HR_FORM_TYPES = (
    ('leave_request', 'طلب إجازة'),
    ('permission_request', 'استئذان'),
    ('resumption_after_leave', 'مباشرة عمل'),
    ('loan_request', 'طلب سلفة'),
    ('salary_adjustment', 'تعديل راتب'),
    ('salary_certificate', 'تعريف راتب'),
    ('salary_transfer_commitment', 'التزام جهة العمل بتحويل الراتب'),
    ('promotion', 'ترقية'),
    ('transfer', 'نقل'),
    ('evaluation', 'تقييم موظف'),
    ('warning_notice', 'إنذار'),
    ('custody_receipt', 'استلام عهدة'),
    ('custody_clearance', 'تصفية عهدة'),
    ('clearance', 'إخلاء طرف'),
    ('contract_termination', 'إنهاء عقد'),
    ('final_settlement', 'تصفية نهاية خدمة'),
    ('user_account', 'حساب مستخدم'),
)

HR_FORM_KEYS = tuple(key for key, _ in HR_FORM_TYPES)

_MODULE_PREFIX = 'hr_form_'
_FIRST_ORDER = 200


def hr_form_permission_code(form_key: str) -> str:
    return f'{_MODULE_PREFIX}{form_key}.view'


def register_hr_form_permissions() -> None:
    """تسجيل وحدة لكل نموذج في permissions_registry (تُزامَن مع DB عند migrate)."""
    for index, (key, label) in enumerate(HR_FORM_TYPES):
        register_module(
            f'{_MODULE_PREFIX}{key}',
            name=f'نموذج — {label}',
            icon='file-text',
            order=_FIRST_ORDER + index,
        )
        register_permission(hr_form_permission_code(key))


def user_has_any_hr_form_permission(permission_codes) -> bool:
    return any(
        code.startswith(_MODULE_PREFIX) and code.endswith('.view')
        for code in permission_codes
    )
