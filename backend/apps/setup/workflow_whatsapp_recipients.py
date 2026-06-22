"""أدوار مستلمي إشعارات واتساب — سير عمل الموافقات."""
from __future__ import annotations

WORKFLOW_WHATSAPP_RECIPIENT_ROLES: tuple[tuple[str, str], ...] = (
    ('system_admin', 'مدير النظام'),
    ('hr_manager', 'مدير الموارد البشرية'),
)

WHATSAPP_ROLE_FIELD_PREFIX = 'workflow_whatsapp_recipient_'
