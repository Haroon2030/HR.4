"""إعدادات إشعارات واتساب لدورة الموافقات."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.core.decorators import permission_required
from apps.core.services.operations_report_whatsapp import whatsapp_delivery_ready
from apps.setup.forms import WorkflowWhatsAppSettingsForm
from apps.setup.models import WorkflowWhatsAppSettings
from apps.setup.workflow_whatsapp_recipients import (
    WORKFLOW_WHATSAPP_RECIPIENT_ROLES,
    WORKFLOW_WHATSAPP_ROLE_GROUPS,
    WHATSAPP_ROLE_FIELD_PREFIX as WORKFLOW_WHATSAPP_PREFIX,
)


@login_required
@permission_required('system_data.edit')
def workflow_whatsapp_settings(request):
    settings_obj = WorkflowWhatsAppSettings.get_solo()

    if request.method == 'POST':
        form = WorkflowWhatsAppSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم حفظ إعدادات واتساب — سير العمل.')
            return redirect(reverse('web:workflow_whatsapp_settings'))
        messages.error(request, 'تحقق من الحقول المدخلة.')
    else:
        form = WorkflowWhatsAppSettingsForm(instance=settings_obj)

    role_labels = dict(WORKFLOW_WHATSAPP_RECIPIENT_ROLES)
    phone_role_groups = [
        (
            group_title,
            [
                (role_labels[key], form[f'{WORKFLOW_WHATSAPP_PREFIX}{key}'])
                for key in role_keys
            ],
        )
        for group_title, role_keys in WORKFLOW_WHATSAPP_ROLE_GROUPS
    ]

    return render(request, 'pages/setup/workflow_whatsapp_settings.html', {
        'form': form,
        'settings_obj': settings_obj,
        'phone_role_groups': phone_role_groups,
        'whatsapp_ready': whatsapp_delivery_ready(),
    })
