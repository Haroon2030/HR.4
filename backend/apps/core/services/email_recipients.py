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


def _append_recipient(recipients: list[str], seen: set[str], addr: str | None) -> None:
    clean = (addr or '').strip()
    if not clean:
        return
    key = clean.lower()
    if key in seen:
        return
    seen.add(key)
    recipients.append(clean)


def resolve_statement_email_recipients(
    employee,
    *,
    posted_employee_email: str,
    posted_hr_email: str,
    actor,
) -> list[str]:
    """
    يُرجع قائمة مستلمين آمنة:
    - بريد الموظف من السجل إذا وُجد و(الحقل فارغ أو يطابق السجل)
    - بريد HR المُدخل إن كان ضمن القائمة المسموحة
    - وإلا يُضاف تلقائياً HR_NOTIFICATION_EMAIL أو بريد المنفّذ إن وُجد
    """
    recipients: list[str] = []
    seen: set[str] = set()

    emp_record = (employee.email or '').strip()
    posted_emp = (posted_employee_email or '').strip()
    if emp_record and (not posted_emp or posted_emp.lower() == emp_record.lower()):
        _append_recipient(recipients, seen, emp_record)

    allowed_hr = allowed_hr_recipients(actor)
    posted_hr = (posted_hr_email or '').strip()
    if posted_hr and posted_hr.lower() in allowed_hr:
        _append_recipient(recipients, seen, posted_hr)

    for candidate in (
        getattr(settings, 'HR_NOTIFICATION_EMAIL', '') or '',
        getattr(actor, 'email', '') or '',
    ):
        c = (candidate or '').strip()
        if c and c.lower() in allowed_hr:
            _append_recipient(recipients, seen, c)

    return recipients
