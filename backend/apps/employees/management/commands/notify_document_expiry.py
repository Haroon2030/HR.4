"""إشعارات داخلية لوثائق تنتهي قريباً (جواز، كرت صحي)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.core.models import Notification, Role
from apps.core.services.notifications import notify
from apps.employees.services.document_expiry import (
    collect_expiring_documents,
    document_expiry_dedupe_prefix,
)
from apps.employees.services.document_expiry_mail import send_document_expiry_summary_email

User = get_user_model()


class Command(BaseCommand):
    help = (
        'يجمع الموظفين الذين تنتهي وثائقهم (جواز / إقامة / كرت صحي / تأمين طبي / عقد مخطط) خلال N يوماً '
        'ويرسل إشعاراً داخلياً لمديري النظام ومديري الموارد البشرية، '
        'ويمكن إرفاق بريد ملخص (--send-email).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='عدد الأيام من اليوم (شامل) لاعتبار الوثيقة «قريبة الانتهاء».',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='يعرض ما سيُرسل دون إنشاء إشعارات أو بريد.',
        )
        parser.add_argument(
            '--cooldown-hours',
            type=int,
            default=20,
            help='تجاهل الإشعار الداخلي إن وُجد بنفس المفتاح لنفس المستلم خلال هذه الساعات.',
        )
        parser.add_argument(
            '--send-email',
            action='store_true',
            help='إرسال بريد ملخص واحد لجميع الصفوف (مستلمون من DOCUMENT_EXPIRY_EMAIL_RECIPIENTS أو بريد مديري الموارد).',
        )

    def handle(self, *args, **options):
        horizon = int(options['days'])
        dry = bool(options['dry_run'])
        cooldown_h = max(0, int(options['cooldown_hours']))
        send_email = bool(options['send_email'])
        ref = timezone.localdate()
        rows = collect_expiring_documents(reference_date=ref, horizon_days=horizon)

        if not rows:
            self.stdout.write(self.style.SUCCESS('لا توجد وثائق ضمن النافذة المحددة.'))
            return

        self.stdout.write(f'تم العثور على {len(rows)} تنبيهاً محتملاً.')

        hr_users: list = []
        if not dry:
            hr_users = list(
                User.objects.filter(
                    is_active=True,
                    profile__role__role_type__in=[
                        Role.RoleType.ADMIN,
                        Role.RoleType.HR_MANAGER,
                    ],
                ).distinct()
            )
            if not hr_users:
                self.stdout.write(
                    self.style.WARNING(
                        'لا يوجد مستخدمون بدور admin أو hr_manager — تخطي الإشعارات الداخلية.'
                    )
                )

        cutoff = timezone.now() - timedelta(hours=cooldown_h)
        sent = 0
        skipped = 0

        for row in rows:
            prefix = document_expiry_dedupe_prefix(
                employee_id=row.employee_id,
                document_code=row.document_code,
                expiry_date=row.expiry_date,
            )
            title = f'{row.document_label} — ينتهي خلال {row.days_until} يوماً'
            if len(title) > 200:
                title = title[:197] + '...'

            try:
                link = reverse('web:edit_employee', kwargs={'employee_id': row.employee_id})
            except NoReverseMatch:
                link = ''

            body = (
                f'{prefix}\n'
                f'الموظف: {row.employee_name}\n'
                f'نوع الوثيقة: {row.document_label}\n'
                f'تاريخ الانتهاء: {row.expiry_date}\n'
                f'الحالة: على رأس العمل أو ما يعادله — راجع الملف وحدّث التواريخ.'
            )

            if dry:
                self.stdout.write(f'[dry-run] {title} | emp={row.employee_id}')
                continue

            for user in hr_users:
                if cooldown_h > 0 and Notification.objects.filter(
                    recipient=user,
                    message__startswith=prefix,
                    created_at__gte=cutoff,
                ).exists():
                    skipped += 1
                    continue
                notify(
                    user,
                    title=title,
                    message=body,
                    link=link,
                    icon='file-earmark-text',
                    color=Notification.Color.AMBER,
                    related_action=None,
                )
                sent += 1

        if dry:
            if send_email:
                self.stdout.write('dry-run: سيُرسل بريد ملخص عند التشغيل بدون --dry-run.')
            self.stdout.write(self.style.SUCCESS('انتهى dry-run.'))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'تم إنشاء {sent} إشعاراً داخلياً (تخطي {skipped} بسبب التهدئة).'
                )
            )

        if send_email and not dry:
            mail_sent = send_document_expiry_summary_email(rows=rows)
            if mail_sent:
                self.stdout.write(self.style.SUCCESS('تم إرسال بريد الملخص.'))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'لم يُرسل بريد (لا مستلمين أو فشل SMTP — راجع السجلات و DOCUMENT_EXPIRY_EMAIL_RECIPIENTS).'
                    )
                )
