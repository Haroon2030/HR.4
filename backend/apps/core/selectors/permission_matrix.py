"""بناء مصفوفة الصلاحيات — أعمدة ديناميكية وصفوف مضغوطة."""
from __future__ import annotations

from apps.core.models import AppModule, Permission, Role
from apps.core.permission_tree import build_permission_tree, display_screen_name
from apps.core.permissions_registry import OPERATION_NAMES, OPERATION_SHORT_LABELS

_OPERATION_ORDER = (
    'view',
    'add',
    'edit',
    'delete',
    'assign',
    'manage',
    'confirm_branch',
    'approve_branch',
    'approve_admin',
    'approve_gm',
    'approve_officer',
    'return',
    'resubmit',
    'execute',
    'workers_view',
    'workers_add',
    'workers_edit',
    'workers_delete',
)


def _operation_label(op_code: str) -> str:
    labels = dict(Permission.Operation.choices)
    return labels.get(op_code) or OPERATION_NAMES.get(op_code, op_code)


def _operation_short_label(op_code: str, full_label: str) -> str:
    return OPERATION_SHORT_LABELS.get(op_code) or full_label[:5]


def _ordered_operations(used_ops: set[str]) -> list[tuple[str, str, str]]:
    ordered: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for op in _OPERATION_ORDER:
        if op in used_ops:
            label = _operation_label(op)
            ordered.append((op, label, _operation_short_label(op, label)))
            seen.add(op)
    for op in sorted(used_ops - seen):
        label = _operation_label(op)
        ordered.append((op, label, _operation_short_label(op, label)))
    return ordered


def build_role_permissions_matrix(role: Role | None) -> dict:
    """جدول وحدات × عمليات لصلاحيات الدور."""
    modules = list(
        AppModule.objects.filter(is_active=True)
        .prefetch_related('permissions')
        .order_by('order', 'name')
    )
    is_admin_role = bool(role and role.role_type == Role.RoleType.ADMIN)
    role_perm_ids = set(role.permissions.values_list('id', flat=True)) if role else set()

    perms_by_module: dict[str, dict[str, Permission]] = {}
    used_ops: set[str] = set()
    for module in modules:
        op_map: dict[str, Permission] = {}
        for perm in module.permissions.all():
            if not perm.is_active:
                continue
            op_map[perm.operation] = perm
            used_ops.add(perm.operation)
        if op_map:
            perms_by_module[module.code] = op_map

    operations = _ordered_operations(used_ops)
    matrix = []
    active_module_codes: set[str] = set()
    for module in modules:
        op_map = perms_by_module.get(module.code, {})
        if not op_map:
            continue
        active_module_codes.add(module.code)
        cells = []
        for op_code, op_label, _op_short in operations:
            perm = op_map.get(op_code)
            cells.append({
                'op_code': op_code,
                'op_label': op_label,
                'perm': perm,
                'checked': bool(perm and (is_admin_role or perm.id in role_perm_ids)),
                'available': perm is not None,
            })
        matrix.append({'module': module, 'cells': cells, 'module_code': module.code})

    permission_tree, module_to_group, default_group_id = build_permission_tree(active_module_codes)
    for row in matrix:
        row['group_id'] = module_to_group.get(row['module_code'], 'other')
        row['screen_name'] = display_screen_name(row['module'].name, row['group_id'])

    return {
        'role': role,
        'is_admin_role': is_admin_role,
        'operations': operations,
        'matrix': matrix,
        'permission_tree': permission_tree,
        'default_group_id': default_group_id,
    }


def build_user_permissions_matrix(*, role, is_admin_user: bool, role_perm_ids: set[int],
                                  extra_ids: set[int], denied_ids: set[int]) -> dict:
    """جدول صلاحيات المستخدم (مسموح / ممنوع فوق الدور)."""
    modules = list(
        AppModule.objects.filter(is_active=True)
        .prefetch_related('permissions')
        .order_by('order', 'name')
    )

    perms_by_module: dict[str, dict[str, Permission]] = {}
    used_ops: set[str] = set()
    for module in modules:
        op_map: dict[str, Permission] = {}
        for perm in module.permissions.all():
            if not perm.is_active:
                continue
            op_map[perm.operation] = perm
            used_ops.add(perm.operation)
        if op_map:
            perms_by_module[module.code] = op_map

    operations = _ordered_operations(used_ops)
    matrix = []
    active_module_codes: set[str] = set()
    for module in modules:
        op_map = perms_by_module.get(module.code, {})
        if not op_map:
            continue
        active_module_codes.add(module.code)
        cells = []
        for op_code, op_label, _op_short in operations:
            perm = op_map.get(op_code)
            if not perm:
                cells.append({'op_code': op_code, 'op_label': op_label, 'available': False})
                continue
            in_role = perm.id in role_perm_ids
            if perm.id in denied_ids:
                state = 'deny'
            elif perm.id in extra_ids:
                state = 'grant'
            else:
                state = 'inherit'
            effective = is_admin_user or (state == 'grant') or (state == 'inherit' and in_role)
            cells.append({
                'op_code': op_code,
                'op_label': op_label,
                'perm': perm,
                'available': True,
                'in_role': in_role,
                'state': state,
                'effective': effective,
            })
        matrix.append({'module': module, 'cells': cells, 'module_code': module.code})

    permission_tree, module_to_group, default_group_id = build_permission_tree(active_module_codes)
    for row in matrix:
        row['group_id'] = module_to_group.get(row['module_code'], 'other')
        row['screen_name'] = display_screen_name(row['module'].name, row['group_id'])

    return {
        'operations': operations,
        'matrix': matrix,
        'permission_tree': permission_tree,
        'default_group_id': default_group_id,
    }
