"""
Permissions Registry — تسجيل تلقائي للوحدات والصلاحيات.

عند استخدام `@permission_required('module.op')` على أي view،
يتم تسجيل (module, operation) تلقائياً في هذا الـ registry.

ثم تتم مزامنة الـ DB تلقائياً بعد كل migrate (وعند تشغيل السيرفر).

لإضافة وحدة جديدة بمسمى عربي وأيقونة، استعمل:
    from apps.core.permissions_registry import register_module
    register_module('attendance', name='الحضور والانصراف', icon='clock', order=10)

أو دع النظام يستخدم القيم الافتراضية ويعتمد فقط على decorators على الـ views.
"""
from typing import Dict, Set


# ============== التسميات والأيقونات الافتراضية للوحدات المعروفة ==============
# عند تسجيل permission على وحدة جديدة لم تُعرَّف هنا أو عبر register_module(),
# سيتم استخدام code كاسم وأيقونة "package".
DEFAULT_MODULE_META: Dict[str, dict] = {
    'employees':    {'name': 'الموظفين',           'icon': 'users',         'order': 1},
    'branches':     {'name': 'الفروع',             'icon': 'building-2',    'order': 2},
    'departments':  {'name': 'الأقسام',            'icon': 'network',       'order': 3},
    'cost_centers': {'name': 'مراكز التكلفة',       'icon': 'wallet',        'order': 4},
    'users':        {'name': 'المستخدمين والأدوار', 'icon': 'shield-check',  'order': 5},
    'system_data':  {'name': 'بيانات النظام',       'icon': 'database',      'order': 6},
    'hr_forms':     {'name': 'النماذج الرسمية',     'icon': 'file-text',     'order': 7},
    'reports':      {'name': 'التقارير',            'icon': 'bar-chart-3',   'order': 8},
}

# تسميات العمليات
OPERATION_NAMES = {
    'view':   'عرض',
    'add':    'إضافة',
    'edit':   'تعديل',
    'delete': 'حذف',
}

# الـ registry الفعلي: {module_code: {'name', 'icon', 'order', 'operations': set()}}
_REGISTRY: Dict[str, dict] = {}


def register_module(code: str, name: str = None, icon: str = 'package', order: int = 100) -> None:
    """تسجيل وحدة (يدوياً) مع تسمية عربية وأيقونة.

    إذا كانت الوحدة موجودة مسبقاً، يُحدَّث ميتاداتاها.
    استدعِها في `apps.py::ready()` للتطبيقات المخصصة.
    """
    entry = _REGISTRY.setdefault(code, {'operations': set()})
    entry['name'] = name or DEFAULT_MODULE_META.get(code, {}).get('name', code)
    entry['icon'] = icon if icon != 'package' else DEFAULT_MODULE_META.get(code, {}).get('icon', icon)
    entry['order'] = order if order != 100 else DEFAULT_MODULE_META.get(code, {}).get('order', order)


def register_permission(permission_code: str) -> None:
    """تسجيل صلاحية بصيغة 'module.operation' (يُستدعى تلقائياً من decorators)."""
    if not permission_code or '.' not in permission_code:
        return
    module_code, operation = permission_code.split('.', 1)
    if not module_code or not operation:
        return
    entry = _REGISTRY.setdefault(module_code, {'operations': set()})
    # إكمال ميتاداتا الوحدة من الـ defaults إن لم تُسجَّل بعد
    if 'name' not in entry:
        meta = DEFAULT_MODULE_META.get(module_code, {})
        entry['name'] = meta.get('name', module_code)
        entry['icon'] = meta.get('icon', 'package')
        entry['order'] = meta.get('order', 100)
    entry['operations'].add(operation)


def get_registry() -> Dict[str, dict]:
    """إرجاع نسخة من الـ registry الحالي."""
    return {k: {**v, 'operations': set(v['operations'])} for k, v in _REGISTRY.items()}


def sync_to_db(verbose: bool = False) -> tuple:
    """مزامنة الـ registry مع جداول AppModule و Permission.

    يُنشئ الناقص ويُحدّث الموجود ولا يحذف شيئاً (آمن).
    يمنح الأدمن جميع الصلاحيات تلقائياً.

    Returns: (modules_count, perms_count, new_perms_count)
    """
    # استيراد متأخّر لتفادي أخطاء التحميل
    from apps.core.models import AppModule, Permission, Role

    new_perms = 0
    for module_code, entry in _REGISTRY.items():
        module, _ = AppModule.objects.update_or_create(
            code=module_code,
            defaults={
                'name': entry.get('name', module_code),
                'icon': entry.get('icon', 'package'),
                'order': entry.get('order', 100),
                'is_active': True,
            },
        )
        if verbose:
            print(f'  📦 {module.name} ({module_code})')

        for op in sorted(entry['operations']):
            perm_code = f'{module_code}.{op}'
            op_label = OPERATION_NAMES.get(op, op)
            _, created = Permission.objects.update_or_create(
                code=perm_code,
                defaults={
                    'module': module,
                    'operation': op,
                    'name': f'{op_label} {module.name}',
                    'is_active': True,
                },
            )
            if created:
                new_perms += 1
                if verbose:
                    print(f'    ✨ NEW: {perm_code}')

    # منح الأدمن كل الصلاحيات
    all_perms = Permission.objects.filter(is_active=True)
    for role in Role.objects.filter(role_type=Role.RoleType.ADMIN):
        role.permissions.set(all_perms)

    return (
        AppModule.objects.count(),
        all_perms.count(),
        new_perms,
    )
