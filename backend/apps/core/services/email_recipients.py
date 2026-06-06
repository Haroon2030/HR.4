"""تحقق من عناوين البريد المسموح إرسال بيانات HR إليها."""
from __future__ import annotations

from django.conf import settings


def allowed_hr_recipients(actor) -> set[str]:
    """عناوين HR المسموحة (إعدادات النظام + بريد المستخدم المنفّذ)."""
    allowed: set[str] = set()
    for addr in (
        getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '',
        getattr(settings, 'HR_NOTIFICATION_EMAIL', '') or '',
        getattr(actor, 'email', '') or '',
    ):
        addr = addr.strip().lower()
        if addr:
            allowed.add(addr)
    return allowed


def resolve_statement_email_recipients(
    employee,
    *,
    posted_employee_email: str,
    posted_hr_email: str,
    actor,
) -> list[str]:
    """
    يُرجع قائمة مستلمين آمنة فقط:
    - بريد الموظف يجب أن يطابق سجل الموظف
    - بريد HR يجب أن يكون من القائمة المسموحة
    """
    recipients: list[str] = []
    emp_record = (employee.email or '').strip().lower()
    posted_emp = (posted_employee_email or '').strip().lower()
    if posted_emp and emp_record and posted_emp == emp_record:
        recipients.append(employee.email.strip())

    posted_hr = (posted_hr_email or '').strip().lower()
    if posted_hr and posted_hr in allowed_hr_recipients(actor):
        recipients.append(posted_hr_email.strip())

    return recipients
