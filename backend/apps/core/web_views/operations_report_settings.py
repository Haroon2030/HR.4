"""إعدادات تقرير العمليات المجدول."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
        form = OperationsReportSettingsForm(request.POST, instance=settings_obj)

        if action == 'test_send':
            test_email = (request.POST.get('test_recipient') or '').strip()
            recipients = [test_email] if test_email else settings_obj.active_recipient_emails()
            if not recipients:
                messages.error(request, 'حدّد بريداً للاختبار أو احفظ مستلماً واحداً على الأقل في الجدول.')
                return redirect(reverse('web:operations_report_settings'))

            try:
                if test_email:
                    build_and_send_operations_report(
                        recipient=test_email,
                        settings_obj=settings_obj,
                        force=True,
                    )
                    sent_label = test_email
                else:
                    build_and_send_operations_report(
                        settings_obj=settings_obj,
                        force=True,
                    )
                    sent_label = '، '.join(recipients)
            except (SmtpNotConfiguredError, SmtpConnectionError) as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f'فشل إرسال التجربة: {exc}')
            else:
                messages.success(
                    request,
                    f'تم إرسال تقرير تجريبي فعلياً إلى {sent_label} — تحقق من الوارد والـ Spam.',
                )
            return redirect(reverse('web:operations_report_settings'))

        if form.is_valid():
            form.save()
            messages.success(request, 'تم حفظ إعدادات تقرير العمليات.')
            return redirect(reverse('web:operations_report_settings'))

        messages.error(request, 'تعذّر الحفظ — راجع الحقول.')
    else:
        form = OperationsReportSettingsForm(instance=settings_obj)

    local_now = timezone.localtime()
    recipient_rows = [
        {
            'key': key,
            'label': label,
            'field': form[f'{ROLE_FIELD_PREFIX}{key}'],
        }
        for key, label in OPERATIONS_REPORT_RECIPIENT_ROLES
    ]
    return render(request, 'pages/setup/operations_report_settings.html', {
        'form': form,
        'settings_obj': settings_obj,
        'local_now': local_now,
        'email_delivery': email_delivery_status(),
        'recipient_rows': recipient_rows,
    })
