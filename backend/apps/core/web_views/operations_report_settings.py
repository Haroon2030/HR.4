"""إعدادات تقرير العمليات المجدول."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.decorators import permission_required
from apps.core.services.email_delivery import email_delivery_status, is_real_smtp_delivery
from apps.core.services.operations_report_mail import build_and_send_operations_report
from apps.setup.forms import OperationsReportSettingsForm
from apps.setup.models import OperationsReportSettings


@login_required
@permission_required('system_data.edit')
def operations_report_settings(request):
    settings_obj = OperationsReportSettings.get_solo()

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save').strip()
        form = OperationsReportSettingsForm(request.POST, instance=settings_obj)

        if action == 'test_send':
            test_email = (request.POST.get('test_recipient') or settings_obj.recipient_email or '').strip()
            if not test_email:
                messages.error(request, 'حدّد بريداً للاختبار أو احفظ بريداً مستلماً أولاً.')
                return redirect(reverse('web:operations_report_settings'))

            try:
                build_and_send_operations_report(
                    recipient=test_email,
                    settings_obj=settings_obj,
                    force=True,
                )
            except Exception as exc:
                messages.error(request, f'فشل إرسال التجربة: {exc}')
            else:
                if is_real_smtp_delivery():
                    messages.success(request, f'تم إرسال تقرير تجريبي إلى {test_email}.')
                else:
                    messages.warning(
                        request,
                        'تم بناء التقرير لكن لم يُرسَل بريد حقيقي — '
                        'النظام يعمل بوضع التطوير (console). '
                        'أضف EMAIL_HOST و EMAIL_HOST_USER و EMAIL_HOST_PASSWORD في backend/.env '
                        'ثم أعد تشغيل السيرفر.',
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
    return render(request, 'pages/setup/operations_report_settings.html', {
        'form': form,
        'settings_obj': settings_obj,
        'local_now': local_now,
        'email_delivery': email_delivery_status(),
    })
