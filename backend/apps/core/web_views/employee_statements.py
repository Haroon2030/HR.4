"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages



# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.web_views._helpers import (
    employee_branch_access_required,
)
from apps.core.decorators import permission_required

@login_required
@permission_required('employees.edit')
@employee_branch_access_required
def add_employee_statement(request, employee_id):
    """إضافة إفادة / إنذار للموظف مع رقم متسلسل وإرسال بريدي اختياري."""
    from django.utils import timezone
    from django.template.loader import render_to_string
    from django.conf import settings as dj_settings
    from apps.employees.models import Employee, EmployeeStatement
    from apps.employees.forms import EmployeeStatementForm
    from apps.core.services.file_helpers import apply_uploaded_file_rename

    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('web:view_employee', employee_id=employee.id)

    files = request.FILES.copy()
    renamed = apply_uploaded_file_rename(request, 'document')
    if renamed is not None:
        files['document'] = renamed

    form = EmployeeStatementForm(request.POST, files)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:view_employee', employee_id=employee.id)

    cd = form.cleaned_data
    send_email_flag = bool(request.POST.get('send_email'))

    statement = form.save(commit=False)
    statement.employee = employee
    statement.document = files.get('document')
    statement.serial_number = EmployeeStatement.generate_serial(
        cd['statement_type'], year=cd['statement_date'].year
    )
    statement.created_by = request.user
    statement.save()

    employee_email = cd.get('employee_email') or ''
    hr_email = cd.get('hr_email') or ''

    # ── إرسال الإيميل إن طُلب ──
    if send_email_flag:
        recipients = [e for e in [employee_email, hr_email] if e]
        if not recipients:
            messages.warning(
                request,
                f'تم حفظ الإفادة برقم {statement.serial_number} — لكن لم يتم الإرسال (لا يوجد بريد).'
            )
            return redirect('web:view_employee', employee_id=employee.id)

        try:
            STATEMENT_THEMES = {
                'warning': {
                    'header_grad': 'linear-gradient(135deg,#b45309,#f59e0b)',
                    'badge_bg': '#fef3c7', 'badge_fg': '#92400e', 'accent': '#f59e0b',
                    'intro': 'نُحيطكم علماً بصدور إنذار رسمي بحقكم بناءً على ما رصدته إدارة الموارد البشرية، ونأمل منكم تصحيح الملاحظات الواردة أدناه تجنباً لاتخاذ إجراءات أشد.',
                    'closing': 'يُعدّ هذا الإنذار مرحلةً تنبيهية ضمن سياسة المنشأة، وتُحفظ نسخة منه في ملفكم الوظيفي.',
                },
                'final_warning': {
                    'header_grad': 'linear-gradient(135deg,#991b1b,#ef4444)',
                    'badge_bg': '#fee2e2', 'badge_fg': '#991b1b', 'accent': '#ef4444',
                    'intro': 'نُحيطكم علماً بصدور إنذار نهائي بحقكم. هذه آخر مرحلة تنبيهية قبل اتخاذ الإجراءات النظامية المنصوص عليها في لائحة العمل ولوائح المنشأة.',
                    'closing': 'نأمل التقيّد التام بتعليمات العمل، علماً أن أي تكرار قد يترتب عليه إنهاء العلاقة التعاقدية وفق نظام العمل المعمول به.',
                },
                'acknowledgment': {
                    'header_grad': 'linear-gradient(135deg,#1d4ed8,#3b82f6)',
                    'badge_bg': '#dbeafe', 'badge_fg': '#1e40af', 'accent': '#3b82f6',
                    'intro': 'يُرجى الاطلاع على نص الإقرار التالي، والتوقيع عليه وإعادته إلى إدارة الموارد البشرية.',
                    'closing': 'يُعدّ توقيعكم على هذا الإقرار موافقةً صريحة على ما ورد فيه.',
                },
                'statement': {
                    'header_grad': 'linear-gradient(135deg,#0f766e,#14b8a6)',
                    'badge_bg': '#ccfbf1', 'badge_fg': '#115e59', 'accent': '#14b8a6',
                    'intro': 'نُحيطكم علماً بصدور إفادة رسمية بشأنكم من إدارة الموارد البشرية بالتفاصيل الموضّحة أدناه.',
                    'closing': 'تُحفظ نسخة من هذه الإفادة في ملفكم الوظيفي للرجوع إليها عند الحاجة.',
                },
                'other': {
                    'header_grad': 'linear-gradient(135deg,#475569,#64748b)',
                    'badge_bg': '#e2e8f0', 'badge_fg': '#334155', 'accent': '#64748b',
                    'intro': 'نُحيطكم علماً بصدور المستند الرسمي التالي من إدارة الموارد البشرية.',
                    'closing': 'يُحفظ هذا المستند في ملفكم الوظيفي.',
                },
            }
            ctx = {
                'statement': statement,
                'employee': employee,
                'site_name': 'نظام HR Pro',
                'theme': STATEMENT_THEMES.get(statement.statement_type, STATEMENT_THEMES['other']),
            }
            html_body = render_to_string('emails/employee_statement.html', ctx)
            text_body = (
                f'إفادة رقم: {statement.serial_number}\n'
                f'الموظف: {employee.name}\n'
                f'النوع: {statement.get_statement_type_display()}\n'
                f'العنوان: {statement.title}\n'
                f'التاريخ: {statement.statement_date}\n\n'
                f'{statement.content or ""}'
            )
            from django.core.mail import EmailMultiAlternatives
            msg = EmailMultiAlternatives(
                subject=f'[{statement.serial_number}] {statement.get_statement_type_display()} — {employee.name}',
                body=text_body,
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.attach_alternative(html_body, 'text/html')
            if statement.document:
                msg.attach_file(statement.document.path)
            msg.send(fail_silently=False)

            statement.email_sent_at = timezone.now()
            statement.save(update_fields=['email_sent_at'])
            messages.success(
                request,
                f'تم حفظ الإفادة [{statement.serial_number}] وإرسالها إلى: {", ".join(recipients)}'
            )
        except Exception as e:
            statement.email_error = str(e)[:500]
            statement.save(update_fields=['email_error'])
            messages.error(
                request,
                f'تم حفظ الإفادة [{statement.serial_number}] لكن فشل الإرسال: {e}'
            )
    else:
        messages.success(request, f'تم تسجيل الإفادة برقم {statement.serial_number}')

    return redirect('web:view_employee', employee_id=employee.id)


@login_required
@permission_required('employees.delete')
@employee_branch_access_required
def delete_employee_statement(request, statement_id):
    """حذف إفادة / إنذار."""
    from apps.employees.models import EmployeeStatement
    statement = get_object_or_404(EmployeeStatement, id=statement_id)
    employee_id = statement.employee_id
    if request.method == 'POST':
        statement.delete()
        messages.success(request, 'تم حذف الإفادة')
    return redirect('web:edit_employee', employee_id=employee_id)


