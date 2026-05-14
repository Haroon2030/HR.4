import json as _json
from django import template

register = template.Library()


@register.filter
def from_json(value):
    """Parse a JSON string and return a dict; returns None on failure."""
    try:
        return _json.loads(value)
    except Exception:
        return None


import re
from django.utils.safestring import mark_safe

@register.filter
def format_archive_text(value):
    """
    يقوم بتحويل النصوص العادية (التي تحتوي على فواصل مثل ─── أو ═══) 
    إلى عناصر HTML احترافية (Cards / Sections) لتبدو أكثر تنظيماً في الأرشيف الزمني.
    """
    if not value:
        return ""
    
    value_str = str(value)
    # Check if text contains structural elements
    if '───' not in value_str and '═══' not in value_str:
        return value_str
        
    lines = value_str.split('\n')
    html = ['<div class="mt-2 space-y-1.5 text-[11px]">']
    
    current_block = []
    
    def flush_block():
        if not current_block: return
        content = "<br>".join(current_block)
        
        # Highlight key-value pairs (bolding the key)
        content = re.sub(r'^([^:\n]+):', r'<span class="font-bold text-slate-700">\1:</span>', content, flags=re.MULTILINE)
        
        # Highlight total
        content = content.replace('★ إجمالي المستحقات:', '<span class="font-bold text-emerald-700 text-xs inline-flex items-center gap-1 mt-1"><i data-lucide="coins" class="w-3.5 h-3.5"></i> إجمالي المستحقات:</span>')
        content = content.replace('* إجمالي المستحقات:', '<span class="font-bold text-emerald-700 text-xs inline-flex items-center gap-1 mt-1"><i data-lucide="coins" class="w-3.5 h-3.5"></i> إجمالي المستحقات:</span>')
        
        # Highlight basic salary changes
        content = content.replace('←', '<i data-lucide="arrow-left" class="w-3 h-3 text-primary-500 inline mx-1"></i>')
        
        html.append(f'<div class="bg-white border border-slate-200 rounded p-2 shadow-sm text-slate-600 leading-relaxed">{content}</div>')
        current_block.clear()

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if '═══' in line:
            flush_block()
            title = line.replace('═══', '').strip()
            html.append(f'<div class="font-bold text-primary-700 text-xs mt-3 mb-1 border-b border-primary-100 pb-1 flex items-center gap-1"><i data-lucide="receipt" class="w-3.5 h-3.5"></i> {title}</div>')
        elif '───' in line:
            flush_block()
        elif line.startswith('ملاحظات:'):
            flush_block()
            html.append(f'<div class="text-slate-500 bg-slate-50 rounded p-1.5 border border-slate-100 mt-1 italic"><span class="font-bold">ملاحظات:</span> {line.replace("ملاحظات:", "").strip()}</div>')
        else:
            current_block.append(line)
            
    flush_block()
    html.append('</div>')
    return mark_safe('\n'.join(html))




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
    
    الاستخدام:
        {% if request.user|has_permission:'employees.edit' %}
            <button>تعديل</button>
        {% endif %}
    """
    from apps.core.decorators import has_permission as check_permission
    return check_permission(user, permission_code)

@register.simple_tag(takes_context=True)
def user_has_permission(context, permission_code):
    """
    Template tag للتحقق من صلاحية المستخدم
    
    الاستخدام:
        {% user_has_permission 'employees.edit' as can_edit %}
        {% if can_edit %}
            <button>تعديل</button>
        {% endif %}
    """
    from apps.core.decorators import has_permission as check_permission
    user = context.get('request').user if 'request' in context else None
    if not user:
        return False
    return check_permission(user, permission_code)

@register.simple_tag(takes_context=True)
def user_permissions(context):
    """
    الحصول على كل صلاحيات المستخدم
    
    الاستخدام:
        {% user_permissions as perms %}
        {% if 'employees.edit' in perms %}
            <button>تعديل</button>
        {% endif %}
    """
    from apps.core.decorators import get_user_permissions
    user = context.get('request').user if 'request' in context else None
    if not user:
        return []
    return get_user_permissions(user)
