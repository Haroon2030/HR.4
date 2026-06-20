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
from apps.core.services.operations_report_schedule import (
    operations_report_schedule_status,
    pick_test_report_date,
)
from apps.core.services.operations_report_whatsapp import whatsapp_delivery_ready
from apps.core.services.whatsapp import phone_utils
from apps.setup.forms import OperationsReportSettingsForm
from apps.setup.models import OperationsReportSettings
from apps.setup.operations_report_recipients import (
    OPERATIONS_REPORT_RECIPIENT_ROLES,
    ROLE_FIELD_PREFIX,
    WHATSAPP_ROLE_FIELD_PREFIX,
)


@login_required
@permission_required('system_data.edit')
def operations_report_settings(request):
    settings_obj = OperationsReportSettings.get_solo()

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save').strip()

        if action == 'link_recipient':
            return _link_recipient_ajax(request, settings_obj, channel='email')

        if action == 'link_whatsapp_recipient':
            return _link_recipient_ajax(request, settings_obj, channel='whatsapp')

        form = OperationsReportSettingsForm(request.POST, instance=settings_obj)

        if action == 'test_send':
            test_email = (request.POST.get('test_recipient') or '').strip()
            test_phone = (request.POST.get('test_recipient_phone') or '').strip()
            recipients = [test_email] if test_email else settings_obj.active_recipient_emails()
            phones = [test_phone] if test_phone else (
                settings_obj.active_recipient_phones() if settings_obj.send_via_whatsapp else []
            )
            if not recipients and not phones:
                messages.error(
                    request,
                    'حدّد بريداً أو جوالاً للاختبار، أو احفظ مستلماً واحداً على الأقل في الجدول.',
                )
                return redirect(reverse('web:operations_report_settings'))

            try:
                now = timezone.localtime()
                report_date, used_fallback = pick_test_report_date(
                    now,
                    settings_obj,
                    include_pending=settings_obj.include_pending,
                    include_completed=settings_obj.include_completed,
                )
                if test_email or test_phone:
                    sent = build_and_send_operations_report(
                        report_date=report_date,
                        recipient=test_email or None,
                        recipient_phone=test_phone or None,
                        settings_obj=settings_obj,
                        force=True,
                        send_email=bool(test_email),
                        send_whatsapp=bool(test_phone),
                        allow_empty=True,
                    )
                else:
                    sent = build_and_send_operations_report(
                        report_date=report_date,
                        settings_obj=settings_obj,
                        force=True,
                        allow_empty=True,
                    )
                labels = []
                if test_email:
                    labels.append(test_email)
                elif recipients:
                    labels.append('بريد: ' + '، '.join(recipients))
                if test_phone:
                    labels.append(test_phone)
                elif phones:
                    labels.append('واتساب: ' + '، '.join(phones))
                sent_label = ' | '.join(labels)
            except (SmtpNotConfiguredError, SmtpConnectionError) as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f'فشل إرسال التجربة: {exc}')
            else:
                if sent:
                    messages.success(
                        request,
                        f'تم إرسال تقرير تجريبي فعلياً إلى {sent_label} — تاريخ التقرير: {report_date.isoformat()}.',
                    )
                    if used_fallback:
                        messages.info(
                            request,
                            f'تم اختيار تاريخ {report_date.isoformat()} لأنه يحتوي بيانات '
                            f'(التاريخ المجدول الافتراضي لم يُظهر عمليات).',
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
                        f'تعذّر الإرسال — تحقق من البريد أو واتساب. '
                        f'تاريخ التقرير: {report_date.isoformat()}. '
                        'ملاحظة: التقرير يشمل طلبات الموافقات والتوظيف فقط — '
                        'التعديل المباشر على ملف الموظف لا يظهر هنا.',
                    )
            return redirect(reverse('web:operations_report_settings'))

        if form.is_valid():
            form.save()
            settings_obj = OperationsReportSettings.get_solo()
            if settings_obj.is_enabled:
                tz = timezone.get_current_timezone_name()
                channels = ['بريد']
                if settings_obj.send_via_whatsapp:
                    channels.append('واتساب')
                messages.success(
                    request,
                    f'تم الحفظ — الإرسال التلقائي مفعّل يومياً الساعة '
                    f'{settings_obj.send_time.strftime("%H:%M")} ({tz}) عبر {" و".join(channels)}.',
                )
            else:
                messages.success(request, 'تم حفظ إعدادات تقرير العمليات.')
            return redirect(reverse('web:operations_report_settings'))

        messages.error(request, 'تعذّر الحفظ — راجع الحقول.')
    else:
        form = OperationsReportSettingsForm(instance=settings_obj)

    stored_emails = settings_obj.recipient_emails_map() if settings_obj.pk else {}
    stored_phones = settings_obj.recipient_phones_map() if settings_obj.pk else {}
    local_now = timezone.localtime()
    recipient_rows = [
        {
            'key': key,
            'label': label,
            'field': form[f'{ROLE_FIELD_PREFIX}{key}'],
            'phone_field': form[f'{WHATSAPP_ROLE_FIELD_PREFIX}{key}'],
            'saved_email': (stored_emails.get(key, '') or '').strip(),
            'saved_phone': (stored_phones.get(key, '') or '').strip(),
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
        'whatsapp_delivery': whatsapp_delivery_ready(),
        'recipient_rows': recipient_rows,
    })


def _link_recipient_ajax(request, settings_obj: OperationsReportSettings, *, channel: str):
    """ربط بريد أو جوال مستلم لدور واحد دون حفظ بقية الإعدادات."""
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'طلب غير صالح.'}, status=400)

    valid_keys = {key for key, _ in OPERATIONS_REPORT_RECIPIENT_ROLES}
    role_key = (request.POST.get('role_key') or '').strip()

    if role_key not in valid_keys:
        return JsonResponse({'success': False, 'message': 'دور غير معروف.'}, status=400)

    if channel == 'whatsapp':
        phone = (request.POST.get('phone') or '').strip()
        err = phone_utils.phone_field_error(phone)
        if err:
            return JsonResponse({'success': False, 'message': err}, status=400)

        phones = settings_obj.recipient_phones_map()
        phones[role_key] = phone
        settings_obj.recipient_phones = phones
        settings_obj.save(update_fields=['recipient_phones'])

        return JsonResponse({
            'success': True,
            'message': 'تم ربط رقم الواتساب. فعّل «إرسال عبر واتساب» والإرسال التلقائي ثم احفظ الإعدادات.',
            'role_key': role_key,
            'phone': phone,
        })

    email = (request.POST.get('email') or '').strip()
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
