"""أدوار مستلمي إشعارات واتساب — سير عمل الموافقات."""
from __future__ import annotations

WORKFLOW_WHATSAPP_RECIPIENT_ROLES: tuple[tuple[str, str], ...] = (
    ('system_admin', 'مدير النظام'),
    ('hr_manager', 'مدير الموارد البشرية'),
    ('admin_manager', 'مدير الإدارة'),
    ('branch_manager', 'مدير الفرع'),
    ('hr_officer', 'أخصائي الموارد البشرية'),
    ('branch_accountant', 'محاسب الفرع'),
)

WORKFLOW_WHATSAPP_ROLE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        'إشراف واعتماد عام',
        ('system_admin', 'hr_manager'),
    ),
    (
        'موافقة أولى وتنفيذ',
        ('admin_manager', 'branch_manager', 'hr_officer', 'branch_accountant'),
    ),
)

WHATSAPP_ROLE_FIELD_PREFIX = 'workflow_whatsapp_recipient_'
