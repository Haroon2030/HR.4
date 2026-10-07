"""سياسات الأدوار المحددة بالكود.

المحاسب (BRANCH_ACCOUNTANT) — اطّلاع شامل بلا أي تعديل:
  • كل صلاحيات العرض (مثل مدير الموارد) + التصدير.
  • أدوات الموافقة فقط (تعميد/إرجاع). نطاق التعميد يحدده ربطه كمدير لإدارة (التهيئة → الإدارات)
    أو لفرع، فلا يعمّد إلا موظفي ما يديره.
  • لا إضافة ولا تعديل ولا حذف ولا تنفيذ على أي عملية.
"""
from __future__ import annotations

ACCOUNTANT_ROLE_TYPE = 'branch_accountant'

# أدوات دورة الموافقات التي يحتاجها المعمِّد (ليست تعديلاً على بيانات)
ACCOUNTANT_WORKFLOW_PERMISSIONS = frozenset({
    'operations.approve_admin',
    'operations.approve_branch',
    'operations.return',
})


# صلاحيات «عرض» لشاشات صيانة تُوسَّع تلقائياً إلى صلاحيات كتابة (طلب سريع، إسناد، إغلاق،
# تأكيد، إرجاع) — لا تُمنح للمحاسب حتى لا يحصل على كتابة عبر التوسعة.
ACCOUNTANT_EXCLUDED_CODES = frozenset({
    'maintenance_screen_request_add.view',
    'maintenance_screen_assign.view',
    'maintenance_screen_manager_close.view',
    'maintenance_screen_branch_confirm.view',
    'maintenance_screen_return.view',
})


def is_read_operation(operation: str) -> bool:
    """عملية قراءة فقط: view / view_salary / workers_view / export..."""
    op = operation or ''
    return op in ('view', 'export') or op.startswith('view_') or op.endswith('_view')


def accountant_permission_codes(permissions) -> set[str]:
    """أكواد صلاحيات المحاسب من قائمة صلاحيات (كائنات لها code و operation)."""
    codes = {
        p.code for p in permissions
        if is_read_operation(p.operation) and p.code not in ACCOUNTANT_EXCLUDED_CODES
    }
    codes |= ACCOUNTANT_WORKFLOW_PERMISSIONS
    return codes


def sync_accountant_role(Role, Permission, *, additive_only: bool = False):
    """يطبّق سياسة المحاسب على دوره الموجود (لا يُنشئ الدور).

    additive_only=True: يضيف ما استجد من صلاحيات العرض فقط (يُستعمل بعد كل مزامنة صلاحيات)،
    وإلا يضبط صلاحيات الدور بالكامل (يحذف أي إضافة/تعديل/حذف).
    يرجع الدور أو None.
    """
    role = Role.objects.filter(role_type=ACCOUNTANT_ROLE_TYPE).first()
    if role is None:
        return None
    permissions = list(Permission.objects.filter(is_active=True))
    wanted_codes = accountant_permission_codes(permissions)
    wanted = [p for p in permissions if p.code in wanted_codes]
    if additive_only:
        existing = set(role.permissions.values_list('id', flat=True))
        missing = [p for p in wanted if p.id not in existing]
        if missing:
            role.permissions.add(*missing)
    else:
        role.permissions.set(wanted)
    return role
