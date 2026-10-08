"""
شجرة أنظمة الصلاحيات — تجميع الوحدات تحت أنظمة رئيسية وأقسام فرعية.
"""
from __future__ import annotations

from apps.core.permissions_registry import DEFAULT_MODULE_META

# أنظمة رئيسية ← أقسام ← أكواد الوحدات (أو بادئة)
# المجموعات الأربع تطابق عناوين الشريط الجانبي (templates/components/sidebar_nav.html):
#   الرئيسية ← بيانات الموظفين ← الحضور والانصراف ← الرواتب والمالية ← إدارة التقارير ← النماذج المستندية ← إدارة الصيانة ← إعدادات النظام والاتصال ← بيانات المستخدمين
# عند إضافة وحدة/شاشة جديدة: أضف كودها هنا وعنصرها في الشريط تحت نفس العنوان.
PERMISSION_TREE_CONFIG: list[dict] = [
    {
        'id': 'main',
        'name': 'الرئيسية',
        'icon': 'layout-grid',
        'children': [
            {'id': 'main_operations', 'name': 'طلبات العمليات', 'module_codes': ['operations']},
        ],
    },
    {
        'id': 'hr',
        'name': 'بيانات الموظفين',
        'icon': 'users',
        'children': [
            {'id': 'hr_employees', 'name': 'الموظفون', 'module_codes': ['employees']},
            {'id': 'hr_tabs', 'name': 'تبويبات ملف الموظف', 'module_prefix': 'employee_tab_'},
            {'id': 'hr_leaves', 'name': 'الإجازات', 'module_codes': ['leaves']},
        ],
    },
    {
        'id': 'attendance',
        'name': 'الحضور والانصراف',
        'icon': 'fingerprint',
        'children': [
            {
                'id': 'att_main',
                'name': 'الشاشات',
                'module_codes': [
                    'attendance',
                    'attendance_screen_devices',
                    'attendance_screen_report',
                    'attendance_screen_late_alerts',
                    'attendance_screen_records',
                ],
            },
        ],
    },
    {
        'id': 'finance',
        'name': 'الرواتب والمالية',
        'icon': 'banknote',
        'children': [
            {'id': 'finance_payroll', 'name': 'مسير الرواتب', 'module_codes': ['payroll']},
            {'id': 'finance_cash_shortages', 'name': 'عجز الكاشير', 'module_codes': ['cash_shortages']},
        ],
    },
    {
        'id': 'reports',
        'name': 'إدارة التقارير',
        'icon': 'bar-chart-3',
        'children': [
            {'id': 'reports_main', 'name': 'التقارير', 'module_codes': ['reports']},
        ],
    },
    {
        'id': 'documents',
        'name': 'النماذج المستندية',
        'icon': 'file-text',
        'children': [
            {'id': 'documents_forms', 'name': 'النماذج الرسمية', 'module_codes': ['hr_forms']},
            {'id': 'documents_form_types', 'name': 'أنواع النماذج الرسمية', 'module_prefix': 'hr_form_'},
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
            {'id': 'maint_setup', 'name': 'التهيئة', 'module_codes': ['maintenance_setup']},
        ],
    },
    {
        'id': 'system_setup',
        'name': 'إعدادات النظام والاتصال',
        'icon': 'settings',
        'children': [
            {'id': 'setup_branches', 'name': 'الهيكل التنظيمي — الفروع', 'module_codes': ['branches']},
            {'id': 'setup_departments', 'name': 'الهيكل التنظيمي — الأقسام', 'module_codes': ['departments']},
            {'id': 'setup_cost_centers', 'name': 'الهيكل التنظيمي — مراكز التكلفة', 'module_codes': ['cost_centers']},
            {'id': 'setup_settings', 'name': 'الإعدادات وربط واتساب', 'module_codes': ['settings', 'system_data']},
        ],
    },
    {
        'id': 'tech',
        'name': 'بيانات المستخدمين',
        'icon': 'settings-2',
        'children': [
            {'id': 'tech_users', 'name': 'المستخدمون والأدوار', 'module_codes': ['users']},
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
