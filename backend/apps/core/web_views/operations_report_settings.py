"""إعدادات تقرير العمليات المجدول."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.decorators import permission_required
from apps.core.services.email_delivery import (
    SmtpConnectionError,
    SmtpNotConfiguredError,
    email_delivery_status,
)
from apps.core.services.operations_report_mail import build_and_send_operations_report
from apps.core.services.operations_report_schedule import operations_report_schedule_status, resolve_operations_report_date
from apps.setup.forms import OperationsReportSettingsForm
from apps.setup.models import OperationsReportSettings
from apps.setup.operations_report_recipients import (
    OPERATIONS_REPORT_RECIPIENT_ROLES,
    ROLE_FIELD_PREFIX,
)


@login_required
@permission_required('system_data.edit')
def operations_report_settings(request):
    settings_obj = OperationsReportSettings.get_solo()

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save').strip()

        if action == 'link_recipient':
            return _link_recipient_ajax(request, settings_obj)

        form = OperationsReportSettingsForm(request.POST, instance=settings_obj)

        if action == 'test_send':
            test_email = (request.POST.get('test_recipient') or '').strip()
            recipients = [test_email] if test_email else settings_obj.active_recipient_emails()
            if not recipients:
                messages.error(request, 'حدّد بريداً للاختبار أو احفظ مستلماً واحداً على الأقل في الجدول.')
                return redirect(reverse('web:operations_report_settings'))

            try:
                report_date = resolve_operations_report_date(
                    timezone.localtime(),
                    settings_obj.send_time,
                    manual=False,
                )
                if test_email:
                    sent = build_and_send_operations_report(
                        report_date=report_date,
                        recipient=test_email,
                        settings_obj=settings_obj,
                        force=True,
                    )
                    sent_label = test_email
                else:
                    sent = build_and_send_operations_report(
                        report_date=report_date,
                        settings_obj=settings_obj,
                        force=True,
                    )
                    sent_label = '، '.join(recipients)
            except (SmtpNotConfiguredError, SmtpConnectionError) as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f'فشل إرسال التجربة: {exc}')
            else:
                if sent:
                    messages.success(
                        request,
                        f'تم إرسال تقرير تجريبي فعلياً إلى {sent_label} — تحقق من الوارد والـ Spam.',
                    )
                    if not settings_obj.is_enabled:
                        messages.warning(
                            request,
                            'التجربة نجحت — لكن الإرسال التلقائي غير مفعّل. '
                            'فعّل «تفعيل الإرسال التلقائي» ثم اضغط «حفظ الإعدادات».',
                        )
                else:
                    messages.warning(
                        request,
                        f'لم يُرسل أي تقرير — لا توجد عمليات معلّقة أو مُنجزة لتاريخ '
                        f'{report_date.isoformat()}. '
                        'المُنجز = ما تمت الموافقة عليه في ذلك اليوم. '
                        'جرّب بعد اعتماد طلب، أو فعّل «تضمين المعلّق».',
                    )
            return redirect(reverse('web:operations_report_settings'))

        if form.is_valid():
            form.save()
            settings_obj = OperationsReportSettings.get_solo()
            if settings_obj.is_enabled:
                tz = timezone.get_current_timezone_name()
                messages.success(
                    request,
                    f'تم الحفظ — الإرسال التلقائي مفعّل يومياً الساعة '
                    f'{settings_obj.send_time.strftime("%H:%M")} ({tz}).',
                )
            else:
                messages.success(request, 'تم حفظ إعدادات تقرير العمليات.')
            return redirect(reverse('web:operations_report_settings'))

        messages.error(request, 'تعذّر الحفظ — راجع الحقول.')
    else:
        form = OperationsReportSettingsForm(instance=settings_obj)

    stored_emails = settings_obj.recipient_emails_map() if settings_obj.pk else {}
    local_now = timezone.localtime()
    recipient_rows = [
        {
            'key': key,
            'label': label,
            'field': form[f'{ROLE_FIELD_PREFIX}{key}'],
            'saved_email': (stored_emails.get(key, '') or '').strip(),
        }
        for key, label in OPERATIONS_REPORT_RECIPIENT_ROLES
    ]
    schedule_status = operations_report_schedule_status(settings_obj)
    return render(request, 'pages/setup/operations_report_settings.html', {
        'form': form,
        'settings_obj': settings_obj,
        'local_now': local_now,
        'schedule_status': schedule_status,
        'email_delivery': email_delivery_status(),
        'recipient_rows': recipient_rows,
    })


def _link_recipient_ajax(request, settings_obj: OperationsReportSettings):
    """ربط بريد مستلم لدور واحد دون حفظ بقية الإعدادات."""
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'طلب غير صالح.'}, status=400)

    valid_keys = {key for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES}
    role_key = (request.POST.get('role_key') or '').strip()
    email = (request.POST.get('email') or '').strip()

    if role_key not in valid_keys:
        return JsonResponse({'success': False, 'message': 'دور غير معروف.'}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'success': False, 'message': 'أدخل بريداً إلكترونياً صالحاً.'}, status=400)

    emails = settings_obj.recipient_emails_map()
    emails[role_key] = email
    settings_obj.recipient_emails = emails
    if role_key == 'system_manager':
        settings_obj.recipient_email = email
    settings_obj.save(update_fields=['recipient_emails', 'recipient_email'])

    return JsonResponse({
        'success': True,
        'message': 'تم ربط البريد بنجاح. فعّل «الإرسال التلقائي» واحفظ الإعدادات لتفعيل الجدولة.',
        'role_key': role_key,
        'email': email,
    })
