"""
كتالوج الأدوار — تسمية تقنية موحّدة (رمز إنجليزي + وصف عربي).
يُستخدم في النماذج، أوامر الإعداد، والهجرة.
"""
from __future__ import annotations

import re

from apps.core.models import Role


def role_type_label(role_type: str) -> str:
    """تسمية نوع الدور في القوائم: CODE — الوصف."""
    entry = ROLE_CATALOG.get(role_type)
    if entry:
        return entry['type_label']
    return role_type


def role_type_choices() -> list[tuple[str, str]]:
    return [(code, ROLE_CATALOG[code]['type_label']) for code in ROLE_TYPE_ORDER]


ROLE_TYPE_ORDER = [
    Role.RoleType.ADMIN,
    Role.RoleType.HR_MANAGER,
    Role.RoleType.HR_OFFICER,
    Role.RoleType.ADMIN_MANAGER,
    Role.RoleType.MANAGER,
    Role.RoleType.SPECIALIST,
    Role.RoleType.EMPLOYEE,
]

ROLE_CATALOG: dict[str, dict[str, str]] = {
    Role.RoleType.ADMIN: {
        'code': 'ADMIN',
        'name': 'ADMIN — مدير النظام',
        'type_label': 'ADMIN — مدير النظام (صلاحيات كاملة)',
        'description': (
            'صلاحيات كاملة: مستخدمون، أدوار، إعدادات، فروع، موظفون، رواتب، تقارير، '
            'وجميع مراحل الموافقات.'
        ),
    },
    Role.RoleType.HR_MANAGER: {
        'code': 'HR_MANAGER',
        'name': 'HR_MANAGER — مدير الموارد البشرية',
        'type_label': 'HR_MANAGER — مدير الموارد البشرية (المدير العام)',
        'description': (
            'إدارة شؤون الموظفين على مستوى الشركة، الرواتب، المستخدمون، التقارير الشاملة، '
            'والموافقة العامة (المرحلة الثانية) في دورة الطلبات.'
        ),
    },
    Role.RoleType.HR_OFFICER: {
        'code': 'HR_OFFICER',
        'name': 'HR_OFFICER — منفّذ الموارد البشرية',
        'type_label': 'HR_OFFICER — منفّذ عمليات الموارد البشرية',
        'description': (
            'تنفيذ المهام المُسندة بعد اعتماد المدير العام (المرحلة الأخيرة في دورة الموافقات).'
        ),
    },
    Role.RoleType.ADMIN_MANAGER: {
        'code': 'ADMIN_MANAGER',
        'name': 'ADMIN_MANAGER — مدير الإدارة',
        'type_label': 'ADMIN_MANAGER — مدير الإدارة (موافقة أولى)',
        'description': (
            'الموافقة الأولى على طلبات موظفي الإدارة المعيّنة عليه '
            '(يُربط من التهيئة → الإدارات).'
        ),
    },
    Role.RoleType.MANAGER: {
        'code': 'BRANCH_MANAGER',
        'name': 'BRANCH_MANAGER — مدير الفرع',
        'type_label': 'BRANCH_MANAGER — مدير الفرع (موافقة أولى)',
        'description': (
            'إدارة موظفي الفرع والموافقة الأولى على طلباتهم عند عدم وجود مدير إدارة فعّال.'
        ),
    },
    Role.RoleType.SPECIALIST: {
        'code': 'DATA_SPECIALIST',
        'name': 'DATA_SPECIALIST — أخصائي إدخال البيانات',
        'type_label': 'DATA_SPECIALIST — أخصائي إدخال البيانات',
        'description': 'إدخال وتحديث بيانات الموظفين ضمن نطاق الفروع المعينة (بدون موافقات).',
    },
    Role.RoleType.EMPLOYEE: {
        'code': 'EMPLOYEE',
        'name': 'EMPLOYEE — موظف',
        'type_label': 'EMPLOYEE — موظف (صلاحيات ذاتية)',
        'description': 'عرض البيانات الشخصية وطلب الإجازات فقط.',
    },
}

# أسماء قديمة شائعة → role_type (للهجرة)
LEGACY_ROLE_NAME_TO_TYPE: dict[str, str] = {
    'الأدمن': Role.RoleType.ADMIN,
    'مدير الموارد البشرية': Role.RoleType.HR_MANAGER,
    'الموارد البشرية': Role.RoleType.HR_MANAGER,
    'أخصائي موارد بشرية': Role.RoleType.HR_OFFICER,
    'مدير إدارة': Role.RoleType.ADMIN_MANAGER,
    'مدير فرع': Role.RoleType.MANAGER,
    'أخصائي إدخال البيانات': Role.RoleType.SPECIALIST,
    'موظف': Role.RoleType.EMPLOYEE,
    'مدير المالية': Role.RoleType.MANAGER,
    'المدير التقني': Role.RoleType.ADMIN,
}


def _extract_arabic_label(text: str) -> str:
    """استخراج الاسم العربي من صيغة CODE — الاسم أو الاسم (ملاحظة)."""
    label = (text or '').strip()
    if not label:
        return '—'
    if ' — ' in label:
        label = label.split(' — ', 1)[1].strip()
    label = re.sub(r'\s*\([^)]*\)\s*$', '', label).strip()
    return label or '—'


def arabic_role_label(*, role_type: str | None = None, name: str | None = None) -> str:
    """الاسم العربي للدور فقط — بدون الرمز الإنجليزي."""
    if role_type and role_type in ROLE_CATALOG:
        return _extract_arabic_label(ROLE_CATALOG[role_type]['name'])
    if name:
        return _extract_arabic_label(name)
    return '—'
