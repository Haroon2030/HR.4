"""أدوار مستلمي تقرير العمليات اليومي."""
from __future__ import annotations

OPERATIONS_REPORT_RECIPIENT_ROLES: tuple[tuple[str, str], ...] = (
    ('system_manager', 'مدير النظام'),
    ('hr_manager', 'مدير الموارد البشرية'),
    ('executive_director', 'المدير التنفيذي'),
    ('operations_manager', 'مدير العمليات'),
    ('finance_manager', 'مدير الحسابات'),
    ('data_manager', 'مدير البيانات'),
    ('procurement_manager', 'مدير المشتريات'),
)

ROLE_FIELD_PREFIX = 'recipient_'
WHATSAPP_ROLE_FIELD_PREFIX = 'whatsapp_recipient_'
