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
    WORKFLOW_WHATSAPP_ROLE_GROUPS,
    WHATSAPP_ROLE_FIELD_PREFIX as WORKFLOW_WHATSAPP_PREFIX,
    workflow_recipient_meta,
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

    stored_phones = settings_obj.recipient_phones_map()
    configured_count = sum(1 for phone in stored_phones.values() if phone)

    recipient_groups = []
    for group_title, group_desc, group_icon, role_keys in WORKFLOW_WHATSAPP_ROLE_GROUPS:
        rows = []
        for role_key in role_keys:
            meta = workflow_recipient_meta(role_key)
            if not meta:
                continue
            field = form[f'{WORKFLOW_WHATSAPP_PREFIX}{role_key}']
            rows.append({
                **meta,
                'field': field,
                'saved_phone': stored_phones.get(role_key, ''),
            })
        recipient_groups.append({
            'title': group_title,
            'description': group_desc,
            'icon': group_icon,
            'rows': rows,
        })

    return render(request, 'pages/setup/workflow_whatsapp_settings.html', {
        'form': form,
        'settings_obj': settings_obj,
        'recipient_groups': recipient_groups,
        'whatsapp_ready': whatsapp_delivery_ready(),
        'configured_count': configured_count,
    })
