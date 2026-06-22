"""أدوار مستلمي إشعارات واتساب — سير عمل الموافقات."""
from __future__ import annotations

from typing import TypedDict


class WorkflowEventMeta(TypedDict):
    code: str
    when: str


class WorkflowRecipientMeta(TypedDict):
    key: str
    label: str
    role_type: str
    events: tuple[WorkflowEventMeta, ...]


WORKFLOW_WHATSAPP_RECIPIENT_META: tuple[WorkflowRecipientMeta, ...] = (
    {
        'key': 'system_admin',
        'label': 'مدير النظام',
        'role_type': 'ADMIN',
        'events': (
            {'code': 'workflow.*.created.broadcast', 'when': 'بث عند رفع طلب جديد'},
        ),
    },
    {
        'key': 'hr_manager',
        'label': 'مدير الموارد البشرية',
        'role_type': 'HR_MANAGER',
        'events': (
            {'code': 'workflow.*.created.broadcast', 'when': 'بث عند رفع طلب جديد'},
            {'code': 'workflow.*.pending_gm', 'when': 'تعميد بعد الموافقة الأولى'},
        ),
    },
    {
        'key': 'admin_manager',
        'label': 'مدير الإدارة',
        'role_type': 'ADMIN_MANAGER',
        'events': (
            {'code': 'workflow.*.first_stage.approver', 'when': 'موافقة أولى — طلب مرتبط بإدارة'},
        ),
    },
    {
        'key': 'branch_manager',
        'label': 'مدير الفرع',
        'role_type': 'BRANCH_MANAGER',
        'events': (
            {'code': 'workflow.*.first_stage.approver', 'when': 'موافقة أولى — طلب فرع أو توظيف'},
        ),
    },
    {
        'key': 'hr_officer',
        'label': 'أخصائي الموارد البشرية',
        'role_type': 'HR_OFFICER',
        'events': (
            {'code': 'workflow.*.officer_assigned', 'when': 'عند إسناد الطلب للأخصائي'},
        ),
    },
    {
        'key': 'branch_accountant',
        'label': 'محاسب الفرع',
        'role_type': 'BRANCH_ACCOUNTANT',
        'events': (
            {'code': 'workflow.*.first_stage.accountant', 'when': 'طلبات عجز الكاشير فقط'},
        ),
    },
)

WORKFLOW_WHATSAPP_RECIPIENT_ROLES: tuple[tuple[str, str], ...] = tuple(
    (item['key'], item['label']) for item in WORKFLOW_WHATSAPP_RECIPIENT_META
)

WORKFLOW_WHATSAPP_ROLE_GROUPS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        'إشراف واعتماد عام',
        'بث تنبيهات الإشراف عند إنشاء الطلبات ومرحلة التعميد',
        'shield-check',
        ('system_admin', 'hr_manager'),
    ),
    (
        'موافقة أولى وتنفيذ',
        'تنبيهات المعتمد الأول والأخصائي والمحاسب — مع بديل من الرقم الثابت',
        'git-branch',
        ('admin_manager', 'branch_manager', 'hr_officer', 'branch_accountant'),
    ),
)

WHATSAPP_ROLE_FIELD_PREFIX = 'workflow_whatsapp_recipient_'

_META_BY_KEY = {item['key']: item for item in WORKFLOW_WHATSAPP_RECIPIENT_META}


def workflow_recipient_meta(role_key: str) -> WorkflowRecipientMeta | None:
    return _META_BY_KEY.get(role_key)
