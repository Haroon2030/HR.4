"""
Permissions Registry — تسجيل تلقائي للوحدات والصلاحيات.

عند استخدام `@permission_required('module.op')` على أي view،
يتم تسجيل (module, operation) تلقائياً في هذا الـ registry.

ثم تتم مزامنة الـ DB تلقائياً بعد كل migrate (وعند تشغيل السيرفر).

لإضافة وحدة جديدة بمسمى عربي وأيقونة، استعمل:
    from apps.core.permissions_registry import register_module
    register_module('payroll', name='الرواتب', icon='wallet', order=9)

أو دع النظام يستخدم القيم الافتراضية ويعتمد فقط على decorators على الـ views.
"""
from typing import Dict


# ============== التسميات والأيقونات الافتراضية للوحدات المعروفة ==============
# عند تسجيل permission على وحدة جديدة لم تُعرَّف هنا أو عبر register_module(),
# سيتم استخدام code كاسم وأيقونة "package".
DEFAULT_MODULE_META: Dict[str, dict] = {
    'employees':    {'name': 'الموظفين',           'icon': 'users',         'order': 1},
    'branches':     {'name': 'الفروع',             'icon': 'building-2',    'order': 2},
    'departments':  {'name': 'الأقسام',            'icon': 'network',       'order': 3},
    'cost_centers': {'name': 'مراكز التكلفة',       'icon': 'wallet',        'order': 4},
    'users':        {'name': 'المستخدمون',           'icon': 'shield-check',  'order': 5},
    'system_data':  {'name': 'بيانات النظام',       'icon': 'database',      'order': 6},
    'hr_forms':     {'name': 'النماذج الرسمية',     'icon': 'file-text',     'order': 7},
    'reports':      {'name': 'التقارير',            'icon': 'bar-chart-3',   'order': 8},
    'payroll':      {'name': 'مسير الرواتب',         'icon': 'calculator',    'order': 9},
    'leaves':       {'name': 'الإجازات',            'icon': 'calendar-days', 'order': 10},
    'attendance':   {'name': 'الحضور والبصمة',      'icon': 'fingerprint',   'order': 11},
    'operations':   {'name': 'طلبات العمليات',      'icon': 'list-checks',   'order': 12},
}

# تسميات العمليات
OPERATION_NAMES = {
    'view':   'عرض',
    'add':    'إضافة',
    'edit':   'تعديل',
    'delete': 'حذف',
    'manage': 'إدارة',
    'approve_branch': 'موافقة الفرع',
    'approve_admin': 'موافقة الإدارة',
    'approve_gm': 'موافقة المدير العام',
    'approve_officer': 'تنفيذ موظف الموارد',
    'return': 'إرجاع',
    'resubmit': 'إعادة إرسال',
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


def _upsert_app_module(AppModule, module_code: str, entry: dict):
    """إنشاء/تحديث وحدة مع استعادة السجلات المحذوفة ناعماً."""
    defaults = {
        'name': entry.get('name', module_code),
        'icon': entry.get('icon', 'package'),
        'order': entry.get('order', 100),
        'is_active': True,
    }
    obj = AppModule.all_objects.filter(code=module_code).first()
    if obj:
        if obj.is_deleted:
            obj.restore()
        for key, val in defaults.items():
            setattr(obj, key, val)
        obj.save()
        return obj, False
    return AppModule.objects.create(code=module_code, **defaults), True


def _upsert_permission(Permission, perm_code: str, module, operation: str, name: str):
    """إنشاء/تحديث صلاحية مع استعادة السجلات المحذوفة ناعماً."""
    defaults = {
        'module': module,
        'operation': operation,
        'name': name,
        'is_active': True,
    }
    obj = Permission.all_objects.filter(code=perm_code).first()
    if obj:
        if obj.is_deleted:
            obj.restore()
        for key, val in defaults.items():
            setattr(obj, key, val)
        obj.save()
        return obj, False
    return Permission.objects.create(code=perm_code, **defaults), True


def sync_to_db(verbose: bool = False) -> tuple:
    """مزامنة الـ registry مع جداول AppModule و Permission.

    يُنشئ الناقص ويُحدّث الموجود ولا يحذف شيئاً (آمن).
    يمنح الأدمن جميع الصلاحيات تلقائياً.

    Returns: (modules_count, perms_count, new_perms_count)
    """
    from apps.core.models import AppModule, Permission, Role

    new_perms = 0
    for module_code, entry in _REGISTRY.items():
        module, _ = _upsert_app_module(AppModule, module_code, entry)
        if verbose:
            print(f'  📦 {module.name} ({module_code})')

        for op in sorted(entry['operations']):
            perm_code = f'{module_code}.{op}'
            op_label = OPERATION_NAMES.get(op, op)
            _, created = _upsert_permission(
                Permission,
                perm_code,
                module,
                op,
                f'{op_label} {module.name}',
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
