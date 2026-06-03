import json as _json
import os
import re
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_ROLE_BADGE_CLASS = {
    'admin': 'bg-purple-100 text-purple-800',
    'hr_manager': 'bg-blue-100 text-blue-800',
    'hr_officer': 'bg-indigo-100 text-indigo-800',
    'admin_manager': 'bg-violet-100 text-violet-800',
    'manager': 'bg-emerald-100 text-emerald-800',
    'specialist': 'bg-amber-100 text-amber-800',
    'employee': 'bg-slate-100 text-slate-700',
}


@register.filter
def format_sar(value, style='neutral'):
    """
    تنسيق مبلغ: 1,234.56 ر.س
    style: neutral | deduct | earn | net | gross
    """
    if value is None or value == '':
        return mark_safe('<span class="pay-money pay-money--empty">—</span>')
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return mark_safe('<span class="pay-money pay-money--empty">—</span>')

    style = str(style or 'neutral').strip().lower()
    if style not in ('neutral', 'deduct', 'earn', 'net', 'gross'):
        style = 'neutral'

    formatted = f'{float(amount):,.2f}'
    return mark_safe(
        f'<span class="pay-money pay-money--{style}" dir="ltr">'
        f'<span class="pay-money__val">{formatted}</span>'
        f'<span class="pay-money__cur">ر.س</span>'
        f'</span>'
    )


@register.filter
def from_json(value):
    """Parse a JSON string and return a dict; returns None on failure."""
    try:
        return _json.loads(value)
    except Exception:
        return None


@register.filter
def format_archive_text(value):
    """
    يقوم بتحويل النصوص العادية (التي تحتوي على فواصل مثل ─── أو ═══)
    إلى عناصر HTML — مع تهريب المحتوى لمنع XSS.
    """
    if not value:
        return ""

    value_str = str(value)
    if '───' not in value_str and '═══' not in value_str:
        return escape(value_str)

    lines = value_str.split('\n')
    html = ['<div class="mt-2 space-y-1.5 text-[11px]">']

    current_block = []

    def flush_block():
        if not current_block:
            return
        safe_lines = [escape(line) for line in current_block]
        content = '<br>'.join(safe_lines)

        content = re.sub(
            r'^([^:\n]+):',
            r'<span class="font-bold text-slate-700">\1:</span>',
            content,
            flags=re.MULTILINE,
        )

        content = content.replace(
            '★ إجمالي المستحقات:',
            '<span class="font-bold text-emerald-700 text-xs inline-flex items-center gap-1 mt-1">'
            '<i data-lucide="coins" class="w-3.5 h-3.5"></i> إجمالي المستحقات:</span>',
        )
        content = content.replace(
            '* إجمالي المستحقات:',
            '<span class="font-bold text-emerald-700 text-xs inline-flex items-center gap-1 mt-1">'
            '<i data-lucide="coins" class="w-3.5 h-3.5"></i> إجمالي المستحقات:</span>',
        )
        content = content.replace(
            '←',
            '<i data-lucide="arrow-left" class="w-3 h-3 text-primary-500 inline mx-1"></i>',
        )

        html.append(
            f'<div class="bg-white border border-slate-200 rounded p-2 shadow-sm '
            f'text-slate-600 leading-relaxed">{content}</div>'
        )
        current_block.clear()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if '═══' in line:
            flush_block()
            title = escape(line.replace('═══', '').strip())
            html.append(
                f'<div class="font-bold text-primary-700 text-xs mt-3 mb-1 border-b '
                f'border-primary-100 pb-1 flex items-center gap-1">'
                f'<i data-lucide="receipt" class="w-3.5 h-3.5"></i> {title}</div>'
            )
        elif '───' in line:
            flush_block()
        elif line.startswith('ملاحظات:'):
            flush_block()
            note_body = escape(line.replace('ملاحظات:', '').strip())
            html.append(
                f'<div class="text-slate-500 bg-slate-50 rounded p-1.5 border border-slate-100 '
                f'mt-1 italic"><span class="font-bold">ملاحظات:</span> {note_body}</div>'
            )
        else:
            current_block.append(line)

    flush_block()
    html.append('</div>')
    return mark_safe('\n'.join(html))


@register.filter
def basename(value):
    """اسم الملف فقط من مسار التخزين."""
    if not value:
        return ''
    return os.path.basename(str(value))


@register.filter
def startswith(value, arg):
    """Check if value starts with arg"""
    if value and arg:
        return str(value).startswith(str(arg))
    return False


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary"""
    if dictionary and key:
        return dictionary.get(key)
    return None


@register.simple_tag
def active_class(request, pattern):
    """Return active class if URL matches pattern"""
    import re
    if re.search(pattern, request.path):
        return 'bg-primary-50 text-primary-700'
    return 'text-slate-600 hover:bg-slate-100'


@register.filter
def has_permission(user, permission_code):
    """
    Template filter للتحقق من صلاحية المستخدم
    """
    from apps.core.decorators import has_permission as check_permission
    return check_permission(user, permission_code)


@register.filter
def is_private_lan_ip(value):
    """True إن كان IP شبكة محلية — السحب من السيرفر السحابي غير ممكن."""
    from apps.attendance.validators import is_private_lan_ip as _check

    return _check(str(value))


@register.filter
def is_general_manager(user):
    """مدير عام / مدير موارد / سوبر يوزر — نفس منطق _is_general_manager في الويب."""
    if not user or not user.is_authenticated:
        return False
    from apps.core.web_views._helpers import _is_general_manager
    return _is_general_manager(user)


@register.simple_tag(takes_context=True)
def user_has_permission(context, permission_code):
    """
    Template tag للتحقق من صلاحية المستخدم
    """
    from apps.core.decorators import has_permission as check_permission
    user = context.get('request').user if 'request' in context else None
    if not user:
        return False
    return check_permission(user, permission_code)


@register.filter
def role_technical_code(role_type):
    """رمز الدور التقني من role_catalog."""
    if not role_type:
        return '—'
    try:
        from apps.core.role_catalog import ROLE_CATALOG
        return ROLE_CATALOG.get(role_type, {}).get('code', role_type)
    except Exception:
        return role_type


@register.filter
def role_badge_class(role_type):
    """كلاس شارة الدور حسب النوع."""
    return _ROLE_BADGE_CLASS.get(role_type, 'bg-slate-100 text-slate-700')


@register.simple_tag(takes_context=True)
def user_permissions(context):
    """
    الحصول على كل صلاحيات المستخدم
    """
    from apps.core.decorators import get_user_permissions
    user = context.get('request').user if 'request' in context else None
    if not user:
        return []
    return get_user_permissions(user)
