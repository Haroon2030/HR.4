"""
شجرة أنظمة الصلاحيات — تجميع الوحدات تحت أنظمة رئيسية وأقسام فرعية.
"""
from __future__ import annotations

from apps.core.permissions_registry import DEFAULT_MODULE_META

# أنظمة رئيسية ← أقسام ← أكواد الوحدات (أو بادئة)
PERMISSION_TREE_CONFIG: list[dict] = [
    {
        'id': 'hr',
        'name': 'أنظمة الموارد البشرية',
        'icon': 'users',
        'children': [
            {'id': 'hr_employees', 'name': 'الموظفين', 'module_codes': ['employees']},
            {'id': 'hr_tabs', 'name': 'تبويبات ملف الموظف', 'module_prefix': 'employee_tab_'},
            {'id': 'hr_leaves', 'name': 'الإجازات', 'module_codes': ['leaves']},
            {
                'id': 'hr_attendance',
                'name': 'الحضور والبصمة',
                'module_codes': [
                    'attendance',
                    'attendance_screen_devices',
                    'attendance_screen_report',
                    'attendance_screen_late_alerts',
                    'attendance_screen_records',
                ],
            },
            {'id': 'hr_payroll', 'name': 'مسير الرواتب', 'module_codes': ['payroll']},
            {'id': 'hr_cash_shortages', 'name': 'عجز الكاشير', 'module_codes': ['cash_shortages']},
        ],
    },
    {
        'id': 'org',
        'name': 'الهيكل التنظيمي',
        'icon': 'building-2',
        'children': [
            {'id': 'org_branches', 'name': 'الفروع', 'module_codes': ['branches']},
            {'id': 'org_departments', 'name': 'الأقسام', 'module_codes': ['departments']},
            {'id': 'org_cost_centers', 'name': 'مراكز التكلفة', 'module_codes': ['cost_centers']},
        ],
    },
    {
        'id': 'maintenance',
        'name': 'إدارة الصيانة',
        'icon': 'wrench',
        'children': [
            {
                'id': 'maint_operations',
                'name': 'العمليات',
                'module_codes': [
                    'maintenance',
                    'maintenance_screen_requests',
                    'maintenance_screen_request_add',
                    'maintenance_screen_assign',
                    'maintenance_screen_manager_close',
                    'maintenance_screen_branch_confirm',
                    'maintenance_screen_return',
                ],
            },
            {
                'id': 'maint_setup',
                'name': 'التهيئة',
                'module_codes': ['maintenance_setup'],
            },
        ],
    },
    {
        'id': 'workflow',
        'name': 'العمليات والطلبات',
        'icon': 'list-checks',
        'children': [
            {'id': 'workflow_ops', 'name': 'طلبات العمليات', 'module_codes': ['operations']},
        ],
    },
    {
        'id': 'admin',
        'name': 'الإدارة والتقارير',
        'icon': 'settings-2',
        'children': [
            {'id': 'admin_users', 'name': 'المستخدمون والأدوار', 'module_codes': ['users']},
            {'id': 'admin_settings', 'name': 'الإعدادات', 'module_codes': ['settings', 'system_data']},
            {'id': 'admin_reports', 'name': 'التقارير والنماذج', 'module_codes': ['reports', 'hr_forms']},
        ],
    },
]


def _resolve_leaf_codes(leaf: dict, all_codes: set[str]) -> list[str]:
    codes: set[str] = set(leaf.get('module_codes') or [])
    prefix = leaf.get('module_prefix')
    if prefix:
        codes |= {c for c in all_codes if c.startswith(prefix)}
    order_map = {
        code: meta.get('order', 500)
        for code, meta in DEFAULT_MODULE_META.items()
    }
    return sorted(
        (c for c in codes if c in all_codes),
        key=lambda c: (order_map.get(c, 500), c),
    )


def build_permission_tree(module_codes: set[str]) -> tuple[list[dict], dict[str, str], str]:
    """
    يُرجع:
    - شجرة الأنظمة (فقط الأقسام التي لها شاشات)
    - خريطة module_code → group_id
    - أول group_id افتراضي للعرض
    """
    tree: list[dict] = []
    module_to_group: dict[str, str] = {}
    assigned: set[str] = set()
    first_group_id = ''

    for system in PERMISSION_TREE_CONFIG:
        children_out = []
        for leaf in system.get('children', []):
            codes = _resolve_leaf_codes(leaf, module_codes)
            if not codes:
                continue
            for code in codes:
                module_to_group[code] = leaf['id']
                assigned.add(code)
            if not first_group_id:
                first_group_id = leaf['id']
            children_out.append({
                'id': leaf['id'],
                'name': leaf['name'],
                'module_codes': codes,
                'screen_count': len(codes),
            })
        if children_out:
            tree.append({
                'id': system['id'],
                'name': system['name'],
                'icon': system.get('icon', 'package'),
                'children': children_out,
            })

    other_codes = sorted(module_codes - assigned)
    if other_codes:
        group_id = 'other'
        if not first_group_id:
            first_group_id = group_id
        for code in other_codes:
            module_to_group[code] = group_id
        tree.append({
            'id': 'other_system',
            'name': 'أخرى',
            'icon': 'package',
            'children': [{
                'id': group_id,
                'name': 'شاشات أخرى',
                'module_codes': other_codes,
                'screen_count': len(other_codes),
            }],
        })

    return tree, module_to_group, first_group_id


def display_screen_name(module_name: str, group_id: str) -> str:
    """اسم مختصر في جدول الصيانة."""
    prefix = 'صيانة — '
    if group_id.startswith('maint_') and module_name.startswith(prefix):
        return module_name[len(prefix):]
    return module_name
