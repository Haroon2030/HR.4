"""إرسال جدول الدوام — بريد رسمي + PDF."""
from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.services.work_schedule_context import build_schedule_boxes_context
from apps.core.services.work_schedule_pdf import build_work_schedule_pdf

SITE_NAME = 'نظام HR Pro'


def _build_text_body(*, employee, boxes_ctx: list[dict]) -> str:
    lines = [
        f'جدول الدوام الرسمي — {employee.name}',
        '',
        'السلام عليكم ورحمة الله وبركاته،',
        '',
        'نرفق لكم بيان جدول الدوام الشهري بصيغة PDF. ملخص الأشهر:',
        '',
    ]
    for box in boxes_ctx:
        lines.append(
            f'- {box["month_name"]} {box["year"]}: {box["days_count"]} يوم دوام — {box["shift_title"]}'
        )
        if box.get('days_str'):
            lines.append(f'  أيام الدوام: {box["days_str"]}')
    lines.extend([
        '',
        'يرجى الاطلاع على المرفق والالتزام بما ورد فيه.',
        '',
        'وتفضلوا بقبول فائق الاحترام والتقدير،',
        'إدارة الموارد البشرية',
        f'— {SITE_NAME}',
    ])
    return '\n'.join(lines)


def send_work_schedule_email(*, employee, boxes_data: list[dict], recipients: list[str]) -> None:
    boxes_ctx = build_schedule_boxes_context(boxes_data)
    if not boxes_ctx:
        raise ValueError('لا توجد بيانات جدول لإرسالها.')

    pdf_bytes = build_work_schedule_pdf(employee=employee, boxes=boxes_ctx)
    issued_date = timezone.localdate()
    ctx = {
        'employee': employee,
        'boxes': boxes_ctx,
        'site_name': SITE_NAME,
        'issued_date': issued_date,
    }
    html_body = render_to_string('emails/employee_schedule.html', ctx)
    text_body = _build_text_body(employee=employee, boxes_ctx=boxes_ctx)

    msg = EmailMultiAlternatives(
        subject=f'جدول الدوام الرسمي — {employee.name}',
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    msg.attach_alternative(html_body, 'text/html')
    filename = f'work-schedule-{employee.id}-{issued_date.isoformat()}.pdf'
    msg.attach(filename, pdf_bytes, 'application/pdf')
    msg.send(fail_silently=False)
